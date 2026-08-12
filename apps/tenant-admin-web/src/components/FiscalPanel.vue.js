import { computed, onMounted, reactive, ref } from "vue";
const props = defineProps();
const emit = defineEmits();
const loading = ref(false);
const tab = ref("contexts");
const contexts = ref([]);
const documents = ref([]);
const fiscalProviders = ref([]);
const fiscalCertificates = ref([]);
const fiscalInutilizations = ref([]);
const documentSchemas = ref([]);
const routingPolicies = ref([]);
const fiscalAssemblies = ref([]);
const emissionTriggerRuns = ref([]);
const rules = ref([]);
const catalogs = ref([]);
const catalogSources = ref([]);
const catalogImports = ref([]);
const catalogGovernance = ref(null);
const catalogQuarantine = ref([]);
const catalogImportFile = ref(null);
const classificationRules = ref([]);
const taxRuleSets = ref([]);
const taxCalculation = ref(null);
const taxLines = computed(() => Object.values((taxCalculation.value?.taxes ?? {})));
const legalSources = ref([]);
const strategyRules = ref([]);
const ibptStatus = ref(null);
const ibptSnapshots = ref([]);
const ibptOffline = ref(null);
const ibptProfiles = ref([]);
const documentTransparency = ref(null);
const deliveryPolicies = ref([]);
const selectedRejection = ref(null);
const selectedArtifactDocument = ref(null);
const selectedArtifacts = ref([]);
const readiness = ref(null);
const connections = ref([]);
const institutions = ref([]);
const units = ref([]);
const selectedContext = ref(null);
const resolved = ref(null);
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
const scopes = ref([
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
const taxComponents = ref([
    { tax: "ICMS", incidence: "taxable", base_mode: "operation_total", rate_pct: "0", base_reduction_pct: "0", deferral_pct: "0", suspension_pct: "0", mva_pct: "0", monophase_amount_per_unit: "", deduct_tax_codes: [] },
]);
const taxSimulationForm = reactive({ fiscal_context_id: "", establishment_code: "", operation_type: "sale", item_kind: "product", occurred_on: today, amount: "0.00", quantity: "1", freight: "0.00", insurance: "0.00", other_amount: "0.00", discount: "0.00" });
const legalSourceForm = reactive({ kind: "technical_note", title: "", version_label: "2026.1", valid_from: today, valid_until: "", source_reference: "", source_sha256: "" });
const strategyForm = reactive({ fiscal_context_id: "", establishment_code: "", strategy_type: "withholding", operation_type: "sale", tax_regime: "any", rtc_mode: "any", origin_uf: "", destination_uf: "", valid_from: today, valid_until: "", priority: 100, rate_pct: "0", amount: "0", legal_source_id: "" });
const rtcForm = reactive({ fiscal_context_id: "", establishment_code: "", tax_regime: "any", mode: "optional_emit", valid_from: today, valid_until: "", legal_source_id: "", notes: "" });
const ibptUf = ref("BA");
const ibptProfileForm = reactive({ provider_code: "wwsoftwares", mode: "local_snapshot", valid_from: today, valid_until: "", sync_enabled: false, fallback_enabled: true, fallback_max_age_days: 90, stale_after_days: 120, base_url: "", uf_path: "", notes: "" });
const certificateForm = reactive({ subject_name: "", subject_document: "", serial_number: "", issuer_name: "", valid_from: `${today}T00:00:00Z`, valid_until: `${new Date(Date.now() + 365 * 86400000).toISOString().slice(0, 10)}T23:59:59Z`, fingerprint_sha256: "", secret_ref: "" });
const providerForm = reactive({ provider_code: "SefazNfeProvider", display_name: "", document_type: "NF-e", environment: "homologation", endpoint_url: "", secret_ref: "", certificate_metadata_id: "", enabled: false });
const deliveryPolicyForm = reactive({ code: "fiscal-default", name: "Entrega fiscal padrão", document_type: "any", provider_code: "", environment: "any", valid_from: today, valid_until: "", priority: 100, max_attempts: 3, base_delay_seconds: 30, max_delay_seconds: 1800, backoff_multiplier: "2", jitter_seconds: 0, auto_retry: true, contingency_after_attempts: 3, contingency_mode: "offline", notes: "" });
const inutilizationForm = reactive({ fiscal_profile_id: "", provider_configuration_id: "", document_type: "NF-e", year: new Date().getFullYear(), series: "1", start_number: 1, end_number: 1, reason: "" });
const documentSchemaForm = reactive({ document_type: "NF-e", schema_code: "LOCAL-NFE", version_label: "1.0-local", valid_from: today, valid_until: "", root_element: "NFeDoc", namespace_uri: "", source_reference: "fixture/local", xsd_text: "" });
const routingPolicyForm = reactive({ fiscal_context_id: "", code: "VENDA-PADRAO", name: "Roteamento padrão", operation_type: "sale", recipient_scope: "any", channel_scope: "any", product_document_type: "", service_document_type: "NFS-e", trigger_types: ["manual"], valid_from: today, valid_until: "", priority: 100, financial_cancel_mode: "link_only", fiscal_reversal_debit_account: "", fiscal_reversal_credit_account: "", tax_regime_filter: "", municipality_filter: "", require_financial_contract: false });
const assemblyForm = reactive({ fiscal_context_id: "", fiscal_profile_id: "", source_type: "manual", source_id: "", occurred_on: today, operation_type: "sale", recipient_scope: "individual", channel: "pos", destination_uf: "BA", trigger_type: "manual", recipient_name: "", recipient_document: "", request_emission: false, items_json: '[{"line_id":"1","item_kind":"product","code":"ITEM","description":"Item fiscal","quantity":"1","unit_price":"0.00","discount":"0","total_amount":"0.00","classification":{}}]' });
const assemblyResult = ref(null);
const fiscalConnections = computed(() => connections.value.filter((row) => [
    "SefazNfeProvider", "SefazNfceProvider", "NationalNfseProvider", "MunicipalNfseProvider", "ThirdPartyFiscalProvider",
].includes(row.provider)));
const publishedVersions = computed(() => contexts.value.reduce((total, context) => total + Number(context.active_version ? 1 : 0), 0));
const awaitingProvider = computed(() => documents.value.filter((row) => row.provider_status === "not_configured").length);
const filteredUnits = computed(() => contextForm.institution_id
    ? units.value.filter((unit) => unit.institution_id === contextForm.institution_id)
    : units.value);
const importSources = computed(() => catalogSources.value.filter((row) => !catalogImportForm.catalog_id || row.fiscal_catalog_id === catalogImportForm.catalog_id));
function message(error) {
    const candidate = error;
    return candidate.problem?.detail || (error instanceof Error ? error.message : "Erro inesperado");
}
function idempotency(prefix) { return `${prefix}-${crypto.randomUUID()}`; }
function nullable(value) { return value.trim() ? value.trim() : null; }
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
function formatDate(value) { return value ? new Date(`${value.slice(0, 10)}T00:00:00`).toLocaleDateString("pt-BR") : "—"; }
function contextStatus(row) { return row.status ?? row.state ?? "—"; }
function sourceProfilesLabel(row) {
    const sources = Array.isArray(row.source_profiles) ? row.source_profiles : [];
    return sources.map((source) => `${String(source.provider_key ?? source.provider_type ?? "fonte")}@${String(source.provider_version ?? "1")}`).join(", ") || "—";
}
async function fileToBase64(file) {
    const buffer = new Uint8Array(await file.arrayBuffer());
    let binary = "";
    for (let i = 0; i < buffer.length; i += 0x8000)
        binary += String.fromCharCode(...buffer.subarray(i, i + 0x8000));
    return btoa(binary);
}
function selectCatalogImportFile(event) {
    catalogImportFile.value = event.target.files?.[0] ?? null;
}
async function load() {
    loading.value = true;
    try {
        const [contextResult, documentResult, ruleResult, connectionResult, catalogResult, classificationResult, taxRuleSetResult, legalSourceResult, strategyResult, ibptState, ibptSnapshotResult, ibptProfileResult, sourceResult, importResult, governanceResult, quarantineResult, providerResult, certificateResult, inutilizationResult, schemaResult, routingResult, assemblyListResult, triggerResult, deliveryPolicyResult] = await Promise.all([
            request("/fiscal/contexts"),
            request("/fiscal/documents"),
            request("/fiscal/rules"),
            request("/integration-connections"),
            request("/fiscal/catalogs"),
            request("/fiscal/classification-rules"),
            request("/fiscal/tax-rule-sets"),
            request("/fiscal/legal-sources"),
            request("/fiscal/strategy-rules"),
            request("/fiscal/ibpt/operational-status"),
            request("/fiscal/ibpt/snapshots"),
            request("/fiscal/ibpt/provider-profiles"),
            request("/fiscal/catalog-sources"),
            request("/fiscal/catalog-imports"),
            request("/fiscal/catalog-governance/health"),
            request("/fiscal/catalog-quarantine"),
            request("/fiscal/providers"),
            request("/fiscal/certificates"),
            request("/fiscal/inutilizations"),
            request("/fiscal/document-schemas"),
            request("/fiscal/routing-policies"),
            request("/fiscal/document-assemblies"),
            request("/fiscal/emission-trigger-runs"),
            request("/fiscal/delivery-policies"),
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
            const references = await request("/references/catalog");
            institutions.value = references.institutions ?? [];
            units.value = references.units ?? [];
        }
        catch {
            institutions.value = [];
            units.value = [];
        }
        if (selectedContext.value) {
            const current = contexts.value.find((row) => row.id === selectedContext.value?.id);
            if (current)
                await showContext(current);
        }
    }
    catch (error) {
        emit("error", message(error));
    }
    finally {
        loading.value = false;
    }
}
async function createContext() {
    try {
        const created = await post("/fiscal/contexts", {
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
    }
    catch (error) {
        emit("error", message(error));
    }
}
async function showContext(row) {
    try {
        selectedContext.value = await request(`/fiscal/contexts/${row.id}`);
        resolved.value = null;
    }
    catch (error) {
        emit("error", message(error));
    }
}
async function updateContextStatus(status) {
    if (!selectedContext.value)
        return;
    try {
        const updated = await patch(`/fiscal/contexts/${selectedContext.value.id}`, {
            status,
            expected_version: selectedContext.value.version,
        });
        emit("notice", `Contexto fiscal atualizado para ${status}.`);
        selectedContext.value = { ...selectedContext.value, ...updated };
        await load();
    }
    catch (error) {
        emit("error", message(error));
    }
}
function addScope() {
    scopes.value.push({ operation_type: "service_billing", item_kind: "service", recipient_scope: "individual", document_type: "NFS-e" });
}
function removeScope(index) {
    if (scopes.value.length > 1)
        scopes.value.splice(index, 1);
}
async function createVersion() {
    if (!selectedContext.value)
        return;
    try {
        const created = await post(`/fiscal/contexts/${selectedContext.value.id}/versions`, {
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
    }
    catch (error) {
        emit("error", message(error));
    }
}
async function publishVersion(version) {
    if (!selectedContext.value)
        return;
    try {
        await post(`/fiscal/contexts/${selectedContext.value.id}/versions/${version.id}/publish`, {
            expected_context_version: selectedContext.value.version,
            expected_version: version.version,
            reason: "Publicação revisada pela administração fiscal do tenant.",
        }, idempotency("fiscal-context-publish"));
        emit("notice", "Versão fiscal publicada ou programada conforme sua vigência.");
        await load();
    }
    catch (error) {
        emit("error", message(error));
    }
}
async function resolveCurrent() {
    if (!selectedContext.value)
        return;
    try {
        resolved.value = await post("/fiscal/contexts/resolve", {
            ...resolveForm,
            context_id: selectedContext.value.id,
        });
        emit("notice", "Contexto fiscal resolvido e fingerprint calculado.");
    }
    catch (error) {
        resolved.value = null;
        emit("error", message(error));
    }
}
async function createCatalog() {
    try {
        const created = await post("/fiscal/catalogs", { kind: catalogForm.kind, name: catalogForm.name, normalization: catalogForm.normalization, code_pattern: nullable(catalogForm.code_pattern), metadata: {} }, idempotency("fiscal-catalog"));
        catalogVersionForm.catalog_id = created.id;
        emit("notice", `Catálogo ${created.kind} criado.`);
        await load();
    }
    catch (error) {
        emit("error", message(error));
    }
}
async function createCatalogVersion() {
    if (!catalogVersionForm.catalog_id)
        return;
    try {
        const version = await post(`/fiscal/catalogs/${catalogVersionForm.catalog_id}/versions`, {
            version_label: catalogVersionForm.version_label, valid_from: catalogVersionForm.valid_from, valid_until: nullable(catalogVersionForm.valid_until),
            source_name: catalogVersionForm.source_name, source_reference: nullable(catalogVersionForm.source_reference), schema_version: "1", notes: null,
            entries: [{ code: catalogVersionForm.code, description: catalogVersionForm.description, metadata: {} }],
        }, idempotency("fiscal-catalog-version"));
        await post(`/fiscal/catalogs/${catalogVersionForm.catalog_id}/versions/${version.id}/publish`, { expected_version: version.version, reason: "Publicação revisada do catálogo fiscal." }, idempotency("fiscal-catalog-publish"));
        emit("notice", "Versão do catálogo publicada ou programada conforme vigência.");
        await load();
    }
    catch (error) {
        emit("error", message(error));
    }
}
async function createCatalogSource() {
    if (!catalogSourceForm.catalog_id)
        return;
    try {
        await post(`/fiscal/catalogs/${catalogSourceForm.catalog_id}/sources`, {
            provider_type: catalogSourceForm.provider_type, provider_key: catalogSourceForm.provider_key, provider_version: catalogSourceForm.provider_version,
            import_format: catalogSourceForm.import_format, source_reference: nullable(catalogSourceForm.source_reference), encoding: catalogSourceForm.encoding,
            delimiter: catalogSourceForm.delimiter, max_age_days: Number(catalogSourceForm.max_age_days), mapping: {}, schema: {}, notes: null,
        }, idempotency("fiscal-catalog-source"));
        emit("notice", "Fonte/importador fiscal configurado.");
        await load();
    }
    catch (error) {
        emit("error", message(error));
    }
}
async function importCatalogFile() {
    if (!catalogImportForm.catalog_id || !catalogImportForm.source_profile_id || !catalogImportFile.value)
        return;
    try {
        const result = await post(`/fiscal/catalogs/${catalogImportForm.catalog_id}/imports`, {
            source_profile_id: catalogImportForm.source_profile_id, filename: catalogImportFile.value.name,
            content_base64: await fileToBase64(catalogImportFile.value), version_label: catalogImportForm.version_label,
            valid_from: catalogImportForm.valid_from, valid_until: nullable(catalogImportForm.valid_until), schema_version: null, notes: null,
            auto_publish: catalogImportForm.auto_publish,
        }, idempotency("fiscal-catalog-import"));
        emit("notice", result.state === "quarantined" ? "Arquivo colocado em quarentena." : "Snapshot fiscal importado e validado.");
        catalogImportFile.value = null;
        await load();
    }
    catch (error) {
        emit("error", message(error));
        await load();
    }
}
async function publishCatalogImport(run) {
    try {
        const detail = await request(`/fiscal/catalog-imports/${run.id}`);
        const version = detail.catalog_version;
        if (!version)
            throw new Error("A importação não possui versão publicável.");
        await post(`/fiscal/catalog-imports/${run.id}/publish`, { expected_version: Number(version.version), reason: "Publicação do snapshot fiscal validado." }, idempotency("fiscal-catalog-import-publish"));
        emit("notice", "Snapshot fiscal publicado/agendado.");
        await load();
    }
    catch (error) {
        emit("error", message(error));
    }
}
async function rollbackCatalogImport(run) {
    if (!run.catalog_version_id)
        return;
    try {
        await post(`/fiscal/catalogs/${run.fiscal_catalog_id}/versions/${run.catalog_version_id}/rollback`, { effective_from: today, reason: "Rollback administrativo para snapshot fiscal validado." }, idempotency("fiscal-catalog-rollback"));
        emit("notice", "Rollback criado como nova versão imutável.");
        await load();
    }
    catch (error) {
        emit("error", message(error));
    }
}
async function resolveCatalogQuarantine(row) {
    try {
        await post(`/fiscal/catalog-quarantine/${row.id}/resolve`, { action: "discarded", reason: "Arquivo revisado e descartado pela administração fiscal." });
        emit("notice", "Quarentena resolvida.");
        await load();
    }
    catch (error) {
        emit("error", message(error));
    }
}
async function createClassification() {
    try {
        const payload = { fiscal_context_id: classificationForm.fiscal_context_id, establishment_code: nullable(classificationForm.establishment_code), item_kind: classificationForm.item_kind, item_id: nullable(classificationForm.item_id), operation_type: classificationForm.operation_type, valid_from: classificationForm.valid_from, valid_until: nullable(classificationForm.valid_until), priority: Number(classificationForm.priority), tax_configuration: {}, notes: null };
        for (const field of ["ncm", "nbs", "lc116", "cfop", "cest", "cst", "csosn", "cst_ibs_cbs", "cclasstrib", "cbenef", "municipal_code", "cnae"])
            payload[field] = nullable(String(classificationForm[field]));
        const created = await post("/fiscal/classification-rules", payload, idempotency("fiscal-classification"));
        await post(`/fiscal/classification-rules/${created.id}/publish`, { expected_version: created.version, reason: "Classificação fiscal revisada pelo tenant." }, idempotency("fiscal-classification-publish"));
        emit("notice", "Regra de classificação publicada.");
        await load();
    }
    catch (error) {
        emit("error", message(error));
    }
}
async function calculateReadiness() {
    if (!classificationForm.fiscal_context_id)
        return;
    try {
        const params = new URLSearchParams({ fiscal_context_id: classificationForm.fiscal_context_id, occurred_on: classificationForm.valid_from, operation_type: classificationForm.operation_type });
        if (classificationForm.establishment_code)
            params.set("establishment_code", classificationForm.establishment_code);
        readiness.value = await request(`/fiscal/readiness?${params.toString()}`);
        emit("notice", "Prontidão fiscal recalculada.");
    }
    catch (error) {
        readiness.value = null;
        emit("error", message(error));
    }
}
function addTaxComponent() {
    taxComponents.value.push({ tax: "CBS", incidence: "taxable", base_mode: "operation_total", rate_pct: "0", base_reduction_pct: "0", deferral_pct: "0", suspension_pct: "0", mva_pct: "0", monophase_amount_per_unit: "", deduct_tax_codes: [] });
}
function removeTaxComponent(index) { if (taxComponents.value.length > 1)
    taxComponents.value.splice(index, 1); }
async function createTaxRuleSet() {
    try {
        const created = await post("/fiscal/tax-rule-sets", {
            fiscal_context_id: taxRuleForm.fiscal_context_id, code: taxRuleForm.code, name: taxRuleForm.name, establishment_code: nullable(taxRuleForm.establishment_code),
            operation_type: taxRuleForm.operation_type, item_kind: taxRuleForm.item_kind, tax_regime: taxRuleForm.tax_regime, rtc_mode: taxRuleForm.rtc_mode, priority: Number(taxRuleForm.priority), description: null,
        }, idempotency("fiscal-tax-ruleset"));
        taxVersionForm.rule_set_id = created.id;
        emit("notice", "Conjunto tributário criado. Inclua uma versão para torná-lo aplicável.");
        await load();
    }
    catch (error) {
        emit("error", message(error));
    }
}
async function createTaxRuleVersion() {
    if (!taxVersionForm.rule_set_id)
        return;
    try {
        const ruleSet = taxRuleSets.value.find((row) => row.id === taxVersionForm.rule_set_id);
        if (!ruleSet)
            throw new Error("Selecione um conjunto tributário válido.");
        const components = taxComponents.value.map((component) => ({
            tax: component.tax, incidence: component.incidence, base_mode: component.base_mode, rate_pct: String(component.rate_pct || "0"),
            base_reduction_pct: String(component.base_reduction_pct || "0"), deferral_pct: String(component.deferral_pct || "0"), suspension_pct: String(component.suspension_pct || "0"),
            mva_pct: String(component.mva_pct || "0"), monophase_amount_per_unit: nullable(String(component.monophase_amount_per_unit || "")),
            custom_base_key: null, include_amount_keys: [], deduct_amount_keys: [], deduct_tax_codes: component.deduct_tax_codes ?? [], metadata: {},
        }));
        const created = await post(`/fiscal/tax-rule-sets/${ruleSet.id}/versions`, {
            version_label: taxVersionForm.version_label, valid_from: taxVersionForm.valid_from, valid_until: nullable(taxVersionForm.valid_until),
            source_name: taxVersionForm.source_name, source_reference: nullable(taxVersionForm.source_reference), legal_basis: taxVersionForm.legal_basis.split("\n").map((v) => v.trim()).filter(Boolean),
            notes: null, components, expected_rule_set_version: ruleSet.version,
        }, idempotency("fiscal-tax-ruleversion"));
        await post(`/fiscal/tax-rule-sets/${ruleSet.id}/versions/${created.id}/publish`, { expected_rule_set_version: created.rule_set_version, expected_version: created.version, reason: "Regra tributária revisada e publicada pelo tenant." }, idempotency("fiscal-tax-publish"));
        emit("notice", "Versão tributária publicada ou programada conforme vigência.");
        await load();
    }
    catch (error) {
        emit("error", message(error));
    }
}
async function simulateTaxCalculation() {
    try {
        taxCalculation.value = await post("/fiscal/tax-calculations/simulate", {
            fiscal_context_id: taxSimulationForm.fiscal_context_id, establishment_code: nullable(taxSimulationForm.establishment_code), operation_type: taxSimulationForm.operation_type,
            item_kind: taxSimulationForm.item_kind, occurred_on: taxSimulationForm.occurred_on, amount: taxSimulationForm.amount, quantity: taxSimulationForm.quantity,
            freight: taxSimulationForm.freight, insurance: taxSimulationForm.insurance, other_amount: taxSimulationForm.other_amount, discount: taxSimulationForm.discount,
            custom_bases: {}, custom_amounts: {}, expected_taxes: {}, recipient_scope: "any", document_type: "any", item_id: null,
        }, idempotency("fiscal-tax-simulation"));
        emit("notice", "Simulação tributária calculada com snapshot e explicabilidade.");
    }
    catch (error) {
        taxCalculation.value = null;
        emit("error", message(error));
    }
}
async function createLegalSource() {
    try {
        await post("/fiscal/legal-sources", { ...legalSourceForm, valid_until: nullable(legalSourceForm.valid_until), source_reference: nullable(legalSourceForm.source_reference), metadata: {} }, idempotency("fiscal-legal-source"));
        emit("notice", "Fonte normativa versionada publicada.");
        await load();
    }
    catch (error) {
        emit("error", message(error));
    }
}
async function createStrategy() {
    try {
        const parameters = {};
        if (Number(strategyForm.rate_pct))
            parameters.rate_pct = strategyForm.rate_pct;
        if (Number(strategyForm.amount))
            parameters.amount = strategyForm.amount;
        await post("/fiscal/strategy-rules", { ...strategyForm, establishment_code: nullable(strategyForm.establishment_code), origin_uf: nullable(strategyForm.origin_uf), destination_uf: nullable(strategyForm.destination_uf), valid_until: nullable(strategyForm.valid_until), legal_source_id: nullable(strategyForm.legal_source_id), parameters }, idempotency("fiscal-strategy"));
        emit("notice", "Estratégia tributária publicada.");
        await load();
    }
    catch (error) {
        emit("error", message(error));
    }
}
async function createRtcSchedule() {
    try {
        await post("/fiscal/rtc-schedules", { ...rtcForm, establishment_code: nullable(rtcForm.establishment_code), valid_until: nullable(rtcForm.valid_until), legal_source_id: nullable(rtcForm.legal_source_id), notes: nullable(rtcForm.notes) }, idempotency("fiscal-rtc"));
        emit("notice", "Cronograma RTC publicado.");
        await load();
    }
    catch (error) {
        emit("error", message(error));
    }
}
async function syncIbpt() { try {
    await post("/fiscal/ibpt/sync", { ufs: [ibptUf.value] });
    emit("notice", `Sincronização IBPT ${ibptUf.value} enfileirada.`);
    await load();
}
catch (error) {
    emit("error", message(error));
} }
async function loadIbptOffline() { try {
    ibptOffline.value = await request(`/fiscal/ibpt/offline/${ibptUf.value}`);
}
catch (error) {
    emit("error", message(error));
} }
async function rollbackIbpt(snapshot) { try {
    await post(`/fiscal/ibpt/snapshots/${snapshot.id}/rollback`, {});
    emit("notice", `Snapshot IBPT ${snapshot.uf} reativado.`);
    await load();
}
catch (error) {
    emit("error", message(error));
} }
async function createIbptProfile() {
    try {
        const result = await post("/fiscal/ibpt/provider-profiles", {
            provider_code: ibptProfileForm.provider_code, mode: ibptProfileForm.mode, valid_from: ibptProfileForm.valid_from,
            valid_until: nullable(ibptProfileForm.valid_until), sync_enabled: ibptProfileForm.sync_enabled,
            fallback_enabled: ibptProfileForm.fallback_enabled, fallback_max_age_days: ibptProfileForm.fallback_max_age_days,
            stale_after_days: ibptProfileForm.stale_after_days, base_url: nullable(ibptProfileForm.base_url),
            uf_path: nullable(ibptProfileForm.uf_path), notes: nullable(ibptProfileForm.notes),
        }, idempotency("fiscal-ibpt-profile"));
        await post(`/fiscal/ibpt/provider-profiles/${result.id}/publish`, { expected_version: Number(result.version ?? 1), reason: "Publicação administrativa do perfil IBPT versionado." });
        emit("notice", "Perfil IBPT versionado publicado.");
        await load();
    }
    catch (error) {
        emit("error", message(error));
    }
}
async function loadDocumentTransparency(row) {
    try {
        documentTransparency.value = await request(`/fiscal/documents/${row.id}/transparency`);
    }
    catch (error) {
        documentTransparency.value = null;
        emit("error", message(error));
    }
}
async function createFiscalCertificate() {
    try {
        await post("/fiscal/certificates", {
            certificate_type: "a1", subject_name: certificateForm.subject_name, subject_document: nullable(certificateForm.subject_document),
            serial_number: certificateForm.serial_number, issuer_name: certificateForm.issuer_name, valid_from: certificateForm.valid_from,
            valid_until: certificateForm.valid_until, fingerprint_sha256: certificateForm.fingerprint_sha256, secret_ref: certificateForm.secret_ref,
            metadata: { source: "tenant-admin-web" },
        }, idempotency("fiscal-certificate"));
        emit("notice", "Metadados do certificado registrados; a chave privada permanece apenas no secret store.");
        await load();
    }
    catch (error) {
        emit("error", message(error));
    }
}
async function createFiscalProvider() {
    try {
        await post("/fiscal/providers", {
            provider_code: providerForm.provider_code, display_name: providerForm.display_name, document_type: providerForm.document_type,
            environment: providerForm.environment, endpoint_url: nullable(providerForm.endpoint_url), secret_ref: nullable(providerForm.secret_ref),
            certificate_metadata_id: nullable(providerForm.certificate_metadata_id), capabilities: ["issue", "query", "cancel", "substitute", "inutilize", "event", "health"],
            settings: {}, enabled: providerForm.enabled,
        }, idempotency("fiscal-provider"));
        emit("notice", "Provider fiscal salvo. Estado real depende das referências de credenciais/certificado.");
        await load();
    }
    catch (error) {
        emit("error", message(error));
    }
}
async function checkFiscalProvider(row) {
    try {
        const result = await post(`/fiscal/providers/${row.id}/health`, {});
        emit("notice", `Health fiscal: ${result.health}`);
        await load();
    }
    catch (error) {
        emit("error", message(error));
    }
}
async function createDeliveryPolicy() {
    try {
        const result = await post("/fiscal/delivery-policies", {
            ...deliveryPolicyForm, provider_code: nullable(deliveryPolicyForm.provider_code), valid_until: nullable(deliveryPolicyForm.valid_until),
            contingency_after_attempts: deliveryPolicyForm.contingency_after_attempts || null, contingency_mode: deliveryPolicyForm.contingency_after_attempts ? deliveryPolicyForm.contingency_mode : null, notes: nullable(deliveryPolicyForm.notes),
        }, idempotency("fiscal-delivery-policy"));
        await post(`/fiscal/delivery-policies/${result.id}/publish`, { expected_version: Number(result.version ?? 1), reason: "Publicação administrativa da política de entrega fiscal." });
        emit("notice", "Política versionada de retry/contingência publicada.");
        await load();
    }
    catch (error) {
        emit("error", message(error));
    }
}
async function retryFiscalDocument(row) {
    const reason = window.prompt("Motivo do reprocessamento fiscal:", "Reprocessamento manual após análise operacional.");
    if (!reason)
        return;
    try {
        await post(`/fiscal/documents/${row.id}/retry`, { reason, force: false });
        emit("notice", "Reprocessamento fiscal enfileirado conforme a política vigente.");
        await load();
    }
    catch (error) {
        emit("error", message(error));
    }
}
async function renderFiscalDocument(row) {
    try {
        const result = await post(`/fiscal/documents/${row.id}/render`, { force: false });
        emit("notice", `Artefato ${String(result.artifact_type)} gerado · ${String(result.sha256).slice(0, 12)}…`);
        await load();
    }
    catch (error) {
        emit("error", message(error));
    }
}
async function loadDocumentArtifacts(row) {
    try {
        const result = await request(`/fiscal/documents/${row.id}/artifacts`);
        selectedArtifactDocument.value = row;
        selectedArtifacts.value = result.items ?? [];
    }
    catch (error) {
        emit("error", message(error));
    }
}
async function downloadFiscalArtifact(row, artifact) {
    if (!row)
        return;
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
    }
    catch (error) {
        emit("error", message(error));
    }
}
async function loadFiscalRejection(row) {
    try {
        selectedRejection.value = await request(`/fiscal/documents/${row.id}/rejection`);
    }
    catch (error) {
        selectedRejection.value = null;
        emit("error", message(error));
    }
}
async function queryFiscalDocument(row) {
    try {
        await post(`/fiscal/documents/${row.id}/query`, { reason: "Consulta manual solicitada pela administração." });
        emit("notice", "Consulta fiscal enfileirada.");
        await load();
    }
    catch (error) {
        emit("error", message(error));
    }
}
async function cancelFiscalDocument(row) {
    const reason = window.prompt("Motivo do cancelamento fiscal:", "Cancelamento solicitado pela administração.");
    if (!reason)
        return;
    try {
        await post(`/fiscal/documents/${row.id}/cancel`, { reason });
        emit("notice", "Cancelamento registrado/enfileirado conforme o estado do documento.");
        await load();
    }
    catch (error) {
        emit("error", message(error));
    }
}
async function substituteFiscalDocument(row) {
    const reason = window.prompt("Motivo da substituição:", "Substituição fiscal solicitada pela administração.");
    if (!reason)
        return;
    try {
        await post(`/fiscal/documents/${row.id}/substitute`, { source_type: "manual", source_id: `${String(row.source_id)}-sub-${Date.now()}`, totals: {}, payload: { replacement_of: row.id }, reason }, idempotency("fiscal-substitute"));
        emit("notice", "Substituição fiscal enfileirada.");
        await load();
    }
    catch (error) {
        emit("error", message(error));
    }
}
async function requestCorrectionEvent(row) {
    const text = window.prompt("Texto do evento/carta de correção:", "");
    if (!text)
        return;
    try {
        await post(`/fiscal/documents/${row.id}/events`, { event_type: "correction_letter", payload: { text }, reason: "Evento solicitado pela administração." }, idempotency("fiscal-event"));
        emit("notice", "Evento fiscal enfileirado.");
        await load();
    }
    catch (error) {
        emit("error", message(error));
    }
}
async function createFiscalInutilization() {
    try {
        await post("/fiscal/inutilizations", { ...inutilizationForm }, idempotency("fiscal-inutilization"));
        emit("notice", "Inutilização registrada conforme o provider configurado.");
        await load();
    }
    catch (error) {
        emit("error", message(error));
    }
}
async function createDocumentSchema() {
    try {
        const result = await post("/fiscal/document-schemas", { document_type: documentSchemaForm.document_type, schema_code: documentSchemaForm.schema_code, version_label: documentSchemaForm.version_label, valid_from: documentSchemaForm.valid_from, valid_until: nullable(documentSchemaForm.valid_until), root_element: documentSchemaForm.root_element, namespace_uri: nullable(documentSchemaForm.namespace_uri), xsd_text: documentSchemaForm.xsd_text, source_reference: nullable(documentSchemaForm.source_reference), metadata: { imported_from: "tenant_admin" } }, idempotency("fiscal-schema"));
        emit("notice", "Schema fiscal versionado criado em rascunho.");
        await publishDocumentSchema(result);
        await load();
    }
    catch (error) {
        emit("error", message(error));
    }
}
async function publishDocumentSchema(row) {
    try {
        await post(`/fiscal/document-schemas/${row.id}/publish`, { reason: "Publicação administrativa do schema validado localmente.", expected_version: Number(row.version ?? 1) });
        emit("notice", "Schema fiscal publicado.");
        await load();
    }
    catch (error) {
        emit("error", message(error));
    }
}
async function createRoutingPolicy() {
    try {
        const settings = {
            financial_cancel_mode: routingPolicyForm.financial_cancel_mode,
            tax_regimes: routingPolicyForm.tax_regime_filter ? [routingPolicyForm.tax_regime_filter] : [],
            municipality_codes: routingPolicyForm.municipality_filter ? [routingPolicyForm.municipality_filter] : [],
            require_financial_contract: routingPolicyForm.require_financial_contract,
            fiscal_reversal_debit_account: nullable(routingPolicyForm.fiscal_reversal_debit_account),
            fiscal_reversal_credit_account: nullable(routingPolicyForm.fiscal_reversal_credit_account),
        };
        const result = await post("/fiscal/routing-policies", {
            fiscal_context_id: routingPolicyForm.fiscal_context_id, code: routingPolicyForm.code, name: routingPolicyForm.name,
            operation_type: routingPolicyForm.operation_type, recipient_scope: routingPolicyForm.recipient_scope, channel_scope: routingPolicyForm.channel_scope,
            product_document_type: nullable(routingPolicyForm.product_document_type), service_document_type: routingPolicyForm.service_document_type,
            trigger_types: routingPolicyForm.trigger_types, valid_from: routingPolicyForm.valid_from, valid_until: nullable(routingPolicyForm.valid_until),
            priority: routingPolicyForm.priority, settings,
        }, idempotency("fiscal-routing"));
        await post(`/fiscal/routing-policies/${result.id}/publish`, { reason: "Publicação administrativa da política de roteamento.", expected_version: Number(result.version ?? 1) });
        emit("notice", "Política de roteamento publicada.");
        await load();
    }
    catch (error) {
        emit("error", message(error));
    }
}
async function assembleFiscalDocument() {
    try {
        const items = JSON.parse(assemblyForm.items_json);
        assemblyResult.value = await post("/fiscal/document-assemblies", { fiscal_context_id: assemblyForm.fiscal_context_id, fiscal_profile_id: assemblyForm.fiscal_profile_id, source_type: assemblyForm.source_type, source_id: assemblyForm.source_id, occurred_on: assemblyForm.occurred_on, operation_type: assemblyForm.operation_type, recipient_scope: assemblyForm.recipient_scope, channel: assemblyForm.channel, destination_uf: nullable(assemblyForm.destination_uf), trigger_type: assemblyForm.trigger_type, recipient: { name: nullable(assemblyForm.recipient_name), document: nullable(assemblyForm.recipient_document), uf: nullable(assemblyForm.destination_uf) }, items, request_emission: assemblyForm.request_emission, metadata: { requested_from: "tenant_admin" } }, idempotency("fiscal-assembly"));
        emit("notice", assemblyResult.value.state === "blocked_validation" ? "Montagem bloqueada pela validação local." : "Montagem fiscal concluída.");
        await load();
    }
    catch (error) {
        emit("error", message(error));
    }
}
async function evaluateEmissionTrigger(row) {
    try {
        await post("/fiscal/emission-trigger-runs/evaluate", { event_type: row.event_type ?? "SaleCompleted", aggregate_id: row.aggregate_id ?? row.source_id, payload: {} });
        emit("notice", "Gatilho fiscal reavaliado.");
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
    ['tabs', 'tabs', 'context-list', 'version-list', 'context-list', 'context-list', 'version-list', 'context-list', 'version-list', 'version-list', 'details', 'scope-row', 'classification-grid', 'tabs', 'tabs', 'refresh', 'details', 'scope-row', 'classification-grid', 'context-list', 'version-list',];
    // CSS variable injection 
    // CSS variable injection end 
    __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
        ...{ class: ("fiscal-panel") },
    });
    __VLS_elementAsFunction(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
        ...{ class: ("metrics") },
    });
    __VLS_elementAsFunction(__VLS_intrinsicElements.article, __VLS_intrinsicElements.article)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
    (__VLS_ctx.contexts.length);
    __VLS_elementAsFunction(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.article, __VLS_intrinsicElements.article)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
    (__VLS_ctx.publishedVersions);
    __VLS_elementAsFunction(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.article, __VLS_intrinsicElements.article)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
    (__VLS_ctx.documents.length);
    __VLS_elementAsFunction(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.article, __VLS_intrinsicElements.article)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
    (__VLS_ctx.awaitingProvider);
    __VLS_elementAsFunction(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
        ...{ class: ("tabs panel") },
    });
    __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
        ...{ onClick: (...[$event]) => {
                __VLS_ctx.tab = 'contexts';
            } },
        ...{ class: (({ active: __VLS_ctx.tab === 'contexts' })) },
    });
    __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
        ...{ onClick: (...[$event]) => {
                __VLS_ctx.tab = 'catalogs';
            } },
        ...{ class: (({ active: __VLS_ctx.tab === 'catalogs' })) },
    });
    __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
        ...{ onClick: (...[$event]) => {
                __VLS_ctx.tab = 'engine';
            } },
        ...{ class: (({ active: __VLS_ctx.tab === 'engine' })) },
    });
    __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
        ...{ onClick: (...[$event]) => {
                __VLS_ctx.tab = 'strategies';
            } },
        ...{ class: (({ active: __VLS_ctx.tab === 'strategies' })) },
    });
    __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
        ...{ onClick: (...[$event]) => {
                __VLS_ctx.tab = 'routing';
            } },
        ...{ class: (({ active: __VLS_ctx.tab === 'routing' })) },
    });
    __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
        ...{ onClick: (...[$event]) => {
                __VLS_ctx.tab = 'documents';
            } },
        ...{ class: (({ active: __VLS_ctx.tab === 'documents' })) },
    });
    __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
        ...{ onClick: (...[$event]) => {
                __VLS_ctx.tab = 'rules';
            } },
        ...{ class: (({ active: __VLS_ctx.tab === 'rules' })) },
    });
    __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
        ...{ onClick: (__VLS_ctx.load) },
        ...{ class: ("small refresh") },
        disabled: ((__VLS_ctx.loading)),
    });
    (__VLS_ctx.loading ? "Atualizando…" : "Atualizar");
    if (__VLS_ctx.tab === 'contexts') {
        __VLS_elementAsFunction(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
            ...{ class: ("grid-2 forms") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.form, __VLS_intrinsicElements.form)({
            ...{ onSubmit: (__VLS_ctx.createContext) },
            ...{ class: ("panel") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: ("cols") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.input)({
            required: (true),
            maxlength: ("80"),
        });
        (__VLS_ctx.contextForm.code);
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.input)({
            required: (true),
            placeholder: ("00.000.000/0000-00"),
        });
        (__VLS_ctx.contextForm.cnpj);
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.input)({
            required: (true),
        });
        (__VLS_ctx.contextForm.establishment_name);
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.input)({});
        (__VLS_ctx.contextForm.legal_name);
        __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: ("cols") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.select, __VLS_intrinsicElements.select)({
            value: ((__VLS_ctx.contextForm.institution_id)),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
            value: (""),
        });
        for (const [row] of __VLS_getVForSourceType((__VLS_ctx.institutions))) {
            __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
                key: ((row.id)),
                value: ((row.id)),
            });
            (row.label ?? row.trade_name ?? row.legal_name);
        }
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.select, __VLS_intrinsicElements.select)({
            value: ((__VLS_ctx.contextForm.unit_id)),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
            value: (""),
        });
        for (const [row] of __VLS_getVForSourceType((__VLS_ctx.filteredUnits))) {
            __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
                key: ((row.id)),
                value: ((row.id)),
            });
            (row.label ?? row.name);
        }
        __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: ("cols") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.input)({});
        (__VLS_ctx.contextForm.state_registration);
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.input)({});
        (__VLS_ctx.contextForm.municipal_registration);
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.select, __VLS_intrinsicElements.select)({
            value: ((__VLS_ctx.contextForm.provider_connection_id)),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
            value: (""),
        });
        for (const [row] of __VLS_getVForSourceType((__VLS_ctx.fiscalConnections))) {
            __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
                key: ((row.id)),
                value: ((row.id)),
            });
            (row.name);
            (row.provider);
        }
        __VLS_elementAsFunction(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
            ...{ class: ("primary") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: ("panel") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: ("panel-title") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
        (__VLS_ctx.contexts.length);
        __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: ("context-list") },
        });
        for (const [row] of __VLS_getVForSourceType((__VLS_ctx.contexts))) {
            __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                ...{ onClick: (...[$event]) => {
                        if (!((__VLS_ctx.tab === 'contexts')))
                            return;
                        __VLS_ctx.showContext(row);
                    } },
                key: ((row.id)),
                ...{ class: (({ selected: __VLS_ctx.selectedContext?.id === row.id })) },
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
            (row.establishment_name);
            __VLS_elementAsFunction(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
            (row.code);
            (row.cnpj);
            (row.active_version?.tax_regime ?? "sem versão publicada");
            __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({
                ...{ class: ("pill") },
                ...{ class: ((__VLS_ctx.contextStatus(row) === 'active' ? 'ok' : 'warn')) },
            });
            (__VLS_ctx.contextStatus(row));
        }
        if (!__VLS_ctx.contexts.length) {
            __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: ("empty") },
            });
        }
        if (__VLS_ctx.selectedContext) {
            __VLS_elementAsFunction(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
                ...{ class: ("panel") },
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: ("panel-title") },
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
            (__VLS_ctx.selectedContext.establishment_name);
            __VLS_elementAsFunction(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
            (__VLS_ctx.selectedContext.code);
            (__VLS_ctx.selectedContext.cnpj);
            (__VLS_ctx.selectedContext.version);
            __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: ("actions") },
            });
            if (__VLS_ctx.contextStatus(__VLS_ctx.selectedContext) !== 'active') {
                __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                    ...{ onClick: (...[$event]) => {
                            if (!((__VLS_ctx.tab === 'contexts')))
                                return;
                            if (!((__VLS_ctx.selectedContext)))
                                return;
                            if (!((__VLS_ctx.contextStatus(__VLS_ctx.selectedContext) !== 'active')))
                                return;
                            __VLS_ctx.updateContextStatus('active');
                        } },
                    ...{ class: ("small") },
                });
            }
            if (__VLS_ctx.contextStatus(__VLS_ctx.selectedContext) === 'active') {
                __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                    ...{ onClick: (...[$event]) => {
                            if (!((__VLS_ctx.tab === 'contexts')))
                                return;
                            if (!((__VLS_ctx.selectedContext)))
                                return;
                            if (!((__VLS_ctx.contextStatus(__VLS_ctx.selectedContext) === 'active')))
                                return;
                            __VLS_ctx.updateContextStatus('inactive');
                        } },
                    ...{ class: ("small") },
                });
            }
            if (__VLS_ctx.contextStatus(__VLS_ctx.selectedContext) !== 'archived') {
                __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                    ...{ onClick: (...[$event]) => {
                            if (!((__VLS_ctx.tab === 'contexts')))
                                return;
                            if (!((__VLS_ctx.selectedContext)))
                                return;
                            if (!((__VLS_ctx.contextStatus(__VLS_ctx.selectedContext) !== 'archived')))
                                return;
                            __VLS_ctx.updateContextStatus('archived');
                        } },
                    ...{ class: ("small danger") },
                });
            }
            __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                ...{ onClick: (...[$event]) => {
                        if (!((__VLS_ctx.tab === 'contexts')))
                            return;
                        if (!((__VLS_ctx.selectedContext)))
                            return;
                        __VLS_ctx.selectedContext = null;
                    } },
                ...{ class: ("small") },
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: ("details") },
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.b, __VLS_intrinsicElements.b)({});
            (__VLS_ctx.selectedContext.state_registration ?? "—");
            __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.b, __VLS_intrinsicElements.b)({});
            (__VLS_ctx.selectedContext.municipal_registration ?? "—");
            __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.b, __VLS_intrinsicElements.b)({});
            (__VLS_ctx.selectedContext.provider_connection_id ?? "not_configured");
            __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.b, __VLS_intrinsicElements.b)({});
            (__VLS_ctx.selectedContext.active_version_id ?? "—");
            __VLS_elementAsFunction(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
                ...{ class: ("grid-2 forms") },
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.form, __VLS_intrinsicElements.form)({
                ...{ onSubmit: (__VLS_ctx.createVersion) },
                ...{ class: ("panel") },
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: ("cols") },
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.select, __VLS_intrinsicElements.select)({
                value: ((__VLS_ctx.versionForm.tax_regime)),
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
                value: ("simples_nacional"),
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
                value: ("lucro_presumido"),
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
                value: ("lucro_real"),
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
                value: ("normal"),
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
                value: ("mei"),
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
                value: ("imune"),
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
                value: ("isenta"),
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
                value: ("public_entity"),
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
                value: ("other"),
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.select, __VLS_intrinsicElements.select)({
                value: ((__VLS_ctx.versionForm.environment)),
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
                value: ("homologation"),
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
                value: ("production"),
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: ("cols") },
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.input)({
                maxlength: ("2"),
                required: (true),
            });
            (__VLS_ctx.versionForm.uf);
            __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.input)({
                maxlength: ("7"),
                required: (true),
            });
            (__VLS_ctx.versionForm.municipality_code);
            __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: ("cols") },
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.input)({
                type: ("date"),
                required: (true),
            });
            (__VLS_ctx.versionForm.valid_from);
            __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.input)({
                type: ("date"),
            });
            (__VLS_ctx.versionForm.valid_until);
            __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.select, __VLS_intrinsicElements.select)({
                value: ((__VLS_ctx.versionForm.rtc_mode)),
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
                value: ("disabled"),
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
                value: ("simulation_only"),
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
                value: ("optional_emit"),
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
                value: ("required_emit"),
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: ("cols") },
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.input)({
                placeholder: ("NF-e 4.00"),
            });
            (__VLS_ctx.versionForm.layout_version);
            __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.input)({
                placeholder: ("PL_010_V120"),
            });
            (__VLS_ctx.versionForm.schema_version);
            __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: ("cols") },
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.input)({});
            (__VLS_ctx.versionForm.technical_note_version);
            __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.input)({});
            (__VLS_ctx.versionForm.ruleset_version);
            __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.textarea, __VLS_intrinsicElements.textarea)({
                value: ((__VLS_ctx.versionForm.notes)),
                rows: ("3"),
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: ("scope-title") },
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.h3, __VLS_intrinsicElements.h3)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                ...{ onClick: (__VLS_ctx.addScope) },
                ...{ class: ("small") },
                type: ("button"),
            });
            for (const [scope, index] of __VLS_getVForSourceType((__VLS_ctx.scopes))) {
                __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                    key: ((index)),
                    ...{ class: ("scope-row") },
                });
                __VLS_elementAsFunction(__VLS_intrinsicElements.input)({
                    required: (true),
                    placeholder: ("sale"),
                });
                (scope.operation_type);
                __VLS_elementAsFunction(__VLS_intrinsicElements.select, __VLS_intrinsicElements.select)({
                    value: ((scope.item_kind)),
                });
                __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
                    value: ("any"),
                });
                __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
                    value: ("product"),
                });
                __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
                    value: ("service"),
                });
                __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
                    value: ("mixed"),
                });
                __VLS_elementAsFunction(__VLS_intrinsicElements.select, __VLS_intrinsicElements.select)({
                    value: ((scope.recipient_scope)),
                });
                __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
                    value: ("any"),
                });
                __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
                    value: ("individual"),
                });
                __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
                    value: ("company"),
                });
                __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
                    value: ("government"),
                });
                __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
                    value: ("foreign"),
                });
                __VLS_elementAsFunction(__VLS_intrinsicElements.select, __VLS_intrinsicElements.select)({
                    value: ((scope.document_type)),
                });
                __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
                    value: ("any"),
                });
                __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
                    value: ("NF-e"),
                });
                __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
                    value: ("NFC-e"),
                });
                __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
                    value: ("NFS-e"),
                });
                __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                    ...{ onClick: (...[$event]) => {
                            if (!((__VLS_ctx.tab === 'contexts')))
                                return;
                            if (!((__VLS_ctx.selectedContext)))
                                return;
                            __VLS_ctx.removeScope(index);
                        } },
                    ...{ class: ("small danger") },
                    type: ("button"),
                    disabled: ((__VLS_ctx.scopes.length === 1)),
                });
            }
            __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                ...{ class: ("primary") },
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: ("panel") },
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: ("panel-title") },
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
            (__VLS_ctx.selectedContext.versions?.length ?? 0);
            __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: ("version-list") },
            });
            for (const [version] of __VLS_getVForSourceType((__VLS_ctx.selectedContext.versions ?? []))) {
                __VLS_elementAsFunction(__VLS_intrinsicElements.article, __VLS_intrinsicElements.article)({
                    key: ((version.id)),
                });
                __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({});
                __VLS_elementAsFunction(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
                (version.version_number);
                (version.tax_regime);
                __VLS_elementAsFunction(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
                (version.uf);
                (version.municipality_code);
                (__VLS_ctx.formatDate(version.valid_from));
                (__VLS_ctx.formatDate(version.valid_until));
                __VLS_elementAsFunction(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
                (version.environment);
                (version.rtc_mode);
                (version.scopes?.length ?? 0);
                __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({});
                __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({
                    ...{ class: ("pill") },
                    ...{ class: ((version.status === 'published' ? 'ok' : version.status === 'draft' ? 'warn' : '')) },
                });
                (version.status);
                if (version.status === 'draft') {
                    __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                        ...{ onClick: (...[$event]) => {
                                if (!((__VLS_ctx.tab === 'contexts')))
                                    return;
                                if (!((__VLS_ctx.selectedContext)))
                                    return;
                                if (!((version.status === 'draft')))
                                    return;
                                __VLS_ctx.publishVersion(version);
                            } },
                        ...{ class: ("small") },
                    });
                }
            }
            if (!__VLS_ctx.selectedContext.versions?.length) {
                __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                    ...{ class: ("empty") },
                });
            }
            __VLS_elementAsFunction(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
                ...{ class: ("grid-2 forms") },
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.form, __VLS_intrinsicElements.form)({
                ...{ onSubmit: (__VLS_ctx.resolveCurrent) },
                ...{ class: ("panel") },
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: ("cols") },
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.input)({
                type: ("date"),
                required: (true),
            });
            (__VLS_ctx.resolveForm.occurred_on);
            __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.input)({
                required: (true),
            });
            (__VLS_ctx.resolveForm.operation_type);
            __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: ("cols") },
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.select, __VLS_intrinsicElements.select)({
                value: ((__VLS_ctx.resolveForm.item_kind)),
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
                value: ("product"),
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
                value: ("service"),
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
                value: ("mixed"),
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.select, __VLS_intrinsicElements.select)({
                value: ((__VLS_ctx.resolveForm.recipient_scope)),
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
                value: ("individual"),
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
                value: ("company"),
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
                value: ("government"),
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
                value: ("foreign"),
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.select, __VLS_intrinsicElements.select)({
                value: ((__VLS_ctx.resolveForm.document_type)),
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
                value: ("NF-e"),
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
                value: ("NFC-e"),
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
                value: ("NFS-e"),
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                ...{ class: ("primary") },
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: ("panel") },
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
            if (__VLS_ctx.resolved) {
                __VLS_elementAsFunction(__VLS_intrinsicElements.dl, __VLS_intrinsicElements.dl)({});
                __VLS_elementAsFunction(__VLS_intrinsicElements.dt, __VLS_intrinsicElements.dt)({});
                __VLS_elementAsFunction(__VLS_intrinsicElements.dd, __VLS_intrinsicElements.dd)({});
                (__VLS_ctx.resolved.version?.version_number);
                (__VLS_ctx.resolved.version?.tax_regime);
                __VLS_elementAsFunction(__VLS_intrinsicElements.dt, __VLS_intrinsicElements.dt)({});
                __VLS_elementAsFunction(__VLS_intrinsicElements.dd, __VLS_intrinsicElements.dd)({});
                (__VLS_ctx.resolved.version?.valid_from);
                (__VLS_ctx.resolved.version?.valid_until ?? "sem término");
                __VLS_elementAsFunction(__VLS_intrinsicElements.dt, __VLS_intrinsicElements.dt)({});
                __VLS_elementAsFunction(__VLS_intrinsicElements.dd, __VLS_intrinsicElements.dd)({});
                (__VLS_ctx.resolved.scope?.operation_type);
                (__VLS_ctx.resolved.scope?.item_kind);
                (__VLS_ctx.resolved.scope?.document_type);
                __VLS_elementAsFunction(__VLS_intrinsicElements.dt, __VLS_intrinsicElements.dt)({});
                __VLS_elementAsFunction(__VLS_intrinsicElements.dd, __VLS_intrinsicElements.dd)({});
                __VLS_elementAsFunction(__VLS_intrinsicElements.code, __VLS_intrinsicElements.code)({});
                (__VLS_ctx.resolved.sha256);
            }
            else {
                __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                    ...{ class: ("empty") },
                });
            }
        }
    }
    else if (__VLS_ctx.tab === 'catalogs') {
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
        __VLS_elementAsFunction(__VLS_intrinsicElements.select, __VLS_intrinsicElements.select)({
            value: ((__VLS_ctx.catalogForm.kind)),
        });
        for (const [kind] of __VLS_getVForSourceType((['NCM', 'NBS', 'LC116', 'CFOP', 'CEST', 'CST', 'CSOSN', 'CST_IBS_CBS', 'CCLASSTRIB', 'CBENEF', 'CREDITO_PRESUMIDO', 'RTC_TABLE', 'NFSE_CORRELATION', 'MUNICIPAL_CODE', 'TAX_RATE', 'TECHNICAL_NOTE']))) {
            __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
                key: ((kind)),
                value: ((kind)),
            });
            (kind);
        }
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.input)({
            required: (true),
        });
        (__VLS_ctx.catalogForm.name);
        __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: ("cols") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.select, __VLS_intrinsicElements.select)({
            value: ((__VLS_ctx.catalogForm.normalization)),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
            value: ("digits"),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
            value: ("upper_alnum"),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
            value: ("preserve"),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.input)({
            placeholder: ("^[0-9]{8}$"),
        });
        (__VLS_ctx.catalogForm.code_pattern);
        __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
            ...{ class: ("primary") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.form, __VLS_intrinsicElements.form)({
            ...{ onSubmit: (__VLS_ctx.createCatalogVersion) },
            ...{ class: ("panel") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.select, __VLS_intrinsicElements.select)({
            value: ((__VLS_ctx.catalogVersionForm.catalog_id)),
            required: (true),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
            value: (""),
        });
        for (const [row] of __VLS_getVForSourceType((__VLS_ctx.catalogs))) {
            __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
                key: ((row.id)),
                value: ((row.id)),
            });
            (row.kind);
            (row.name);
        }
        __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: ("cols") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.input)({
            required: (true),
        });
        (__VLS_ctx.catalogVersionForm.version_label);
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.input)({
            type: ("date"),
            required: (true),
        });
        (__VLS_ctx.catalogVersionForm.valid_from);
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.input)({
            required: (true),
        });
        (__VLS_ctx.catalogVersionForm.source_name);
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.input)({});
        (__VLS_ctx.catalogVersionForm.source_reference);
        __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: ("cols") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.input)({
            required: (true),
        });
        (__VLS_ctx.catalogVersionForm.code);
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.input)({
            required: (true),
        });
        (__VLS_ctx.catalogVersionForm.description);
        __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
            ...{ class: ("primary") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
            ...{ class: ("grid-2 forms") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.form, __VLS_intrinsicElements.form)({
            ...{ onSubmit: (__VLS_ctx.createClassification) },
            ...{ class: ("panel") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.select, __VLS_intrinsicElements.select)({
            value: ((__VLS_ctx.classificationForm.fiscal_context_id)),
            required: (true),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
            value: (""),
        });
        for (const [row] of __VLS_getVForSourceType((__VLS_ctx.contexts))) {
            __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
                key: ((row.id)),
                value: ((row.id)),
            });
            (row.code);
            (row.establishment_name);
        }
        __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: ("cols") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.input)({
            placeholder: ("MATRIZ-BA"),
        });
        (__VLS_ctx.classificationForm.establishment_code);
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.input)({
            required: (true),
        });
        (__VLS_ctx.classificationForm.operation_type);
        __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: ("cols") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.select, __VLS_intrinsicElements.select)({
            value: ((__VLS_ctx.classificationForm.item_kind)),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
            value: ("product"),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
            value: ("service"),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
            value: ("mixed"),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.input)({});
        (__VLS_ctx.classificationForm.item_id);
        __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: ("cols") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.input)({
            type: ("date"),
            required: (true),
        });
        (__VLS_ctx.classificationForm.valid_from);
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.input)({
            type: ("date"),
        });
        (__VLS_ctx.classificationForm.valid_until);
        __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: ("classification-grid") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.input)({});
        (__VLS_ctx.classificationForm.ncm);
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.input)({});
        (__VLS_ctx.classificationForm.nbs);
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.input)({});
        (__VLS_ctx.classificationForm.lc116);
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.input)({});
        (__VLS_ctx.classificationForm.cfop);
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.input)({});
        (__VLS_ctx.classificationForm.cest);
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.input)({});
        (__VLS_ctx.classificationForm.cst);
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.input)({});
        (__VLS_ctx.classificationForm.csosn);
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.input)({});
        (__VLS_ctx.classificationForm.cst_ibs_cbs);
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.input)({});
        (__VLS_ctx.classificationForm.cclasstrib);
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.input)({});
        (__VLS_ctx.classificationForm.cbenef);
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.input)({});
        (__VLS_ctx.classificationForm.municipal_code);
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.input)({});
        (__VLS_ctx.classificationForm.cnae);
        __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: ("actions") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
            ...{ class: ("primary") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
            ...{ onClick: (__VLS_ctx.calculateReadiness) },
            type: ("button"),
            ...{ class: ("small") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: ("panel") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: ("panel-title") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
        if (__VLS_ctx.readiness) {
            __VLS_elementAsFunction(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
            (__VLS_ctx.readiness.readiness_percentage);
        }
        if (__VLS_ctx.readiness) {
            __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: ("details") },
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.b, __VLS_intrinsicElements.b)({});
            (__VLS_ctx.readiness.total_items);
            __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.b, __VLS_intrinsicElements.b)({});
            (__VLS_ctx.readiness.ready_items);
            __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.b, __VLS_intrinsicElements.b)({});
            (__VLS_ctx.readiness.pending_items);
            __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.b, __VLS_intrinsicElements.b)({});
            (__VLS_ctx.readiness.rtc_mode);
            __VLS_elementAsFunction(__VLS_intrinsicElements.table, __VLS_intrinsicElements.table)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.thead, __VLS_intrinsicElements.thead)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.tr, __VLS_intrinsicElements.tr)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.th, __VLS_intrinsicElements.th)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.th, __VLS_intrinsicElements.th)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.th, __VLS_intrinsicElements.th)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.th, __VLS_intrinsicElements.th)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.tbody, __VLS_intrinsicElements.tbody)({});
            for (const [item] of __VLS_getVForSourceType((__VLS_ctx.readiness.items))) {
                __VLS_elementAsFunction(__VLS_intrinsicElements.tr, __VLS_intrinsicElements.tr)({
                    key: ((item.item_id)),
                });
                __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
                (item.code);
                (item.name);
                __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
                (item.item_kind);
                __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
                __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({
                    ...{ class: ("pill") },
                    ...{ class: ((item.ready ? 'ok' : 'warn')) },
                });
                (item.ready ? 'pronto' : 'pendente');
                __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
                (item.missing?.join(', ') || '—');
            }
        }
        else {
            __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: ("empty") },
            });
        }
        __VLS_elementAsFunction(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
            ...{ class: ("grid-2 forms") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.form, __VLS_intrinsicElements.form)({
            ...{ onSubmit: (__VLS_ctx.createCatalogSource) },
            ...{ class: ("panel") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.select, __VLS_intrinsicElements.select)({
            value: ((__VLS_ctx.catalogSourceForm.catalog_id)),
            required: (true),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
            value: (""),
        });
        for (const [row] of __VLS_getVForSourceType((__VLS_ctx.catalogs))) {
            __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
                key: ((row.id)),
                value: ((row.id)),
            });
            (row.kind);
            (row.name);
        }
        __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: ("cols") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.input)({
            required: (true),
        });
        (__VLS_ctx.catalogSourceForm.provider_key);
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.input)({
            required: (true),
        });
        (__VLS_ctx.catalogSourceForm.provider_version);
        __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: ("cols") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.select, __VLS_intrinsicElements.select)({
            value: ((__VLS_ctx.catalogSourceForm.provider_type)),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
            value: ("local_file"),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
            value: ("manual_snapshot"),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
            value: ("external_http"),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.select, __VLS_intrinsicElements.select)({
            value: ((__VLS_ctx.catalogSourceForm.import_format)),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
            value: ("csv"),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
            value: ("json"),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
            value: ("xsd"),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.input)({
            placeholder: ("Origem/ato/arquivo oficial"),
        });
        (__VLS_ctx.catalogSourceForm.source_reference);
        __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
            ...{ class: ("primary") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.form, __VLS_intrinsicElements.form)({
            ...{ onSubmit: (__VLS_ctx.importCatalogFile) },
            ...{ class: ("panel") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.select, __VLS_intrinsicElements.select)({
            value: ((__VLS_ctx.catalogImportForm.catalog_id)),
            required: (true),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
            value: (""),
        });
        for (const [row] of __VLS_getVForSourceType((__VLS_ctx.catalogs))) {
            __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
                key: ((row.id)),
                value: ((row.id)),
            });
            (row.kind);
            (row.name);
        }
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.select, __VLS_intrinsicElements.select)({
            value: ((__VLS_ctx.catalogImportForm.source_profile_id)),
            required: (true),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
            value: (""),
        });
        for (const [row] of __VLS_getVForSourceType((__VLS_ctx.importSources))) {
            __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
                key: ((row.id)),
                value: ((row.id)),
            });
            (row.provider_key);
            (row.provider_version);
            (row.import_format);
            (row.state);
        }
        __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: ("cols") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.input)({
            required: (true),
        });
        (__VLS_ctx.catalogImportForm.version_label);
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.input)({
            type: ("date"),
            required: (true),
        });
        (__VLS_ctx.catalogImportForm.valid_from);
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.input)({
            ...{ onChange: (__VLS_ctx.selectCatalogImportFile) },
            type: ("file"),
            accept: (".csv,.json,.xsd,text/csv,application/json,application/xml,text/xml"),
            required: (true),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({
            ...{ class: ("inline-check") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.input)({
            type: ("checkbox"),
        });
        (__VLS_ctx.catalogImportForm.auto_publish);
        __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
            ...{ class: ("primary") },
            disabled: ((!__VLS_ctx.catalogImportFile)),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
            ...{ class: ("panel") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: ("panel-title") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
        (__VLS_ctx.catalogGovernance?.missing_kinds?.length ?? 0);
        __VLS_elementAsFunction(__VLS_intrinsicElements.table, __VLS_intrinsicElements.table)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.thead, __VLS_intrinsicElements.thead)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.tr, __VLS_intrinsicElements.tr)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.th, __VLS_intrinsicElements.th)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.th, __VLS_intrinsicElements.th)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.th, __VLS_intrinsicElements.th)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.th, __VLS_intrinsicElements.th)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.tbody, __VLS_intrinsicElements.tbody)({});
        for (const [row] of __VLS_getVForSourceType((__VLS_ctx.catalogGovernance?.catalogs ?? []))) {
            __VLS_elementAsFunction(__VLS_intrinsicElements.tr, __VLS_intrinsicElements.tr)({
                key: ((row.catalog_id)),
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
            (row.kind);
            __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
            (row.active_version?.version_label ?? '—');
            __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
            (__VLS_ctx.sourceProfilesLabel(row));
            __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({
                ...{ class: ("pill") },
                ...{ class: ((row.healthy ? 'ok' : 'warn')) },
            });
            (row.healthy ? 'saudável' : row.reasons.join(', '));
        }
        if (__VLS_ctx.catalogGovernance?.missing_kinds?.length) {
            __VLS_elementAsFunction(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({
                ...{ class: ("warn-text") },
            });
            (__VLS_ctx.catalogGovernance.missing_kinds.join(', '));
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
        (__VLS_ctx.catalogImports.length);
        __VLS_elementAsFunction(__VLS_intrinsicElements.table, __VLS_intrinsicElements.table)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.thead, __VLS_intrinsicElements.thead)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.tr, __VLS_intrinsicElements.tr)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.th, __VLS_intrinsicElements.th)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.th, __VLS_intrinsicElements.th)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.th, __VLS_intrinsicElements.th)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.th, __VLS_intrinsicElements.th)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.th, __VLS_intrinsicElements.th)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.tbody, __VLS_intrinsicElements.tbody)({});
        for (const [row] of __VLS_getVForSourceType((__VLS_ctx.catalogImports))) {
            __VLS_elementAsFunction(__VLS_intrinsicElements.tr, __VLS_intrinsicElements.tr)({
                key: ((row.id)),
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
            (row.version_label);
            __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
            (row.state);
            __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
            (row.entries_count);
            __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.code, __VLS_intrinsicElements.code)({});
            (row.source_sha256);
            __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
            if (row.state === 'draft_created') {
                __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                    ...{ onClick: (...[$event]) => {
                            if (!(!((__VLS_ctx.tab === 'contexts'))))
                                return;
                            if (!((__VLS_ctx.tab === 'catalogs')))
                                return;
                            if (!((row.state === 'draft_created')))
                                return;
                            __VLS_ctx.publishCatalogImport(row);
                        } },
                    ...{ class: ("small") },
                });
            }
            if (row.catalog_version_id && ['published', 'scheduled'].includes(row.state)) {
                __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                    ...{ onClick: (...[$event]) => {
                            if (!(!((__VLS_ctx.tab === 'contexts'))))
                                return;
                            if (!((__VLS_ctx.tab === 'catalogs')))
                                return;
                            if (!((row.catalog_version_id && ['published', 'scheduled'].includes(row.state))))
                                return;
                            __VLS_ctx.rollbackCatalogImport(row);
                        } },
                    ...{ class: ("small") },
                });
            }
        }
        if (!__VLS_ctx.catalogImports.length) {
            __VLS_elementAsFunction(__VLS_intrinsicElements.tr, __VLS_intrinsicElements.tr)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({
                colspan: ("5"),
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
        (__VLS_ctx.catalogQuarantine.length);
        __VLS_elementAsFunction(__VLS_intrinsicElements.table, __VLS_intrinsicElements.table)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.thead, __VLS_intrinsicElements.thead)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.tr, __VLS_intrinsicElements.tr)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.th, __VLS_intrinsicElements.th)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.th, __VLS_intrinsicElements.th)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.th, __VLS_intrinsicElements.th)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.th, __VLS_intrinsicElements.th)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.tbody, __VLS_intrinsicElements.tbody)({});
        for (const [row] of __VLS_getVForSourceType((__VLS_ctx.catalogQuarantine))) {
            __VLS_elementAsFunction(__VLS_intrinsicElements.tr, __VLS_intrinsicElements.tr)({
                key: ((row.id)),
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
            (row.reason_code);
            (row.reason_detail);
            __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.code, __VLS_intrinsicElements.code)({});
            (row.source_sha256);
            __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
            (row.state);
            __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
            if (row.state === 'open') {
                __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                    ...{ onClick: (...[$event]) => {
                            if (!(!((__VLS_ctx.tab === 'contexts'))))
                                return;
                            if (!((__VLS_ctx.tab === 'catalogs')))
                                return;
                            if (!((row.state === 'open')))
                                return;
                            __VLS_ctx.resolveCatalogQuarantine(row);
                        } },
                    ...{ class: ("small danger") },
                });
            }
        }
        if (!__VLS_ctx.catalogQuarantine.length) {
            __VLS_elementAsFunction(__VLS_intrinsicElements.tr, __VLS_intrinsicElements.tr)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({
                colspan: ("4"),
                ...{ class: ("empty") },
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
        (__VLS_ctx.catalogs.length);
        __VLS_elementAsFunction(__VLS_intrinsicElements.table, __VLS_intrinsicElements.table)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.thead, __VLS_intrinsicElements.thead)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.tr, __VLS_intrinsicElements.tr)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.th, __VLS_intrinsicElements.th)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.th, __VLS_intrinsicElements.th)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.th, __VLS_intrinsicElements.th)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.th, __VLS_intrinsicElements.th)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.th, __VLS_intrinsicElements.th)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.tbody, __VLS_intrinsicElements.tbody)({});
        for (const [row] of __VLS_getVForSourceType((__VLS_ctx.catalogs))) {
            __VLS_elementAsFunction(__VLS_intrinsicElements.tr, __VLS_intrinsicElements.tr)({
                key: ((row.id)),
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
            (row.kind);
            __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
            (row.name);
            __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
            (row.active_version?.version_label ?? '—');
            __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
            (row.active_version ? __VLS_ctx.formatDate(row.active_version.valid_from) : '—');
            __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.code, __VLS_intrinsicElements.code)({});
            (row.active_version?.source_sha256 ?? '—');
        }
        if (!__VLS_ctx.catalogs.length) {
            __VLS_elementAsFunction(__VLS_intrinsicElements.tr, __VLS_intrinsicElements.tr)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({
                colspan: ("5"),
                ...{ class: ("empty") },
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
        (__VLS_ctx.classificationRules.length);
        __VLS_elementAsFunction(__VLS_intrinsicElements.table, __VLS_intrinsicElements.table)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.thead, __VLS_intrinsicElements.thead)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.tr, __VLS_intrinsicElements.tr)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.th, __VLS_intrinsicElements.th)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.th, __VLS_intrinsicElements.th)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.th, __VLS_intrinsicElements.th)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.th, __VLS_intrinsicElements.th)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.th, __VLS_intrinsicElements.th)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.tbody, __VLS_intrinsicElements.tbody)({});
        for (const [row] of __VLS_getVForSourceType((__VLS_ctx.classificationRules))) {
            __VLS_elementAsFunction(__VLS_intrinsicElements.tr, __VLS_intrinsicElements.tr)({
                key: ((row.id)),
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.code, __VLS_intrinsicElements.code)({});
            (row.fiscal_context_id);
            __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
            (row.item_kind);
            (row.item_id ?? 'geral');
            __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
            (row.operation_type);
            __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
            (__VLS_ctx.formatDate(row.valid_from));
            (__VLS_ctx.formatDate(row.valid_until));
            __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
            ([row.ncm, row.nbs, row.lc116, row.cfop, row.cest, row.cst, row.csosn, row.cst_ibs_cbs, row.cclasstrib, row.cbenef].filter(Boolean).join(' · ') || '—');
        }
    }
    else if (__VLS_ctx.tab === 'engine') {
        __VLS_elementAsFunction(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
            ...{ class: ("grid-2 forms") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.form, __VLS_intrinsicElements.form)({
            ...{ onSubmit: (__VLS_ctx.createTaxRuleSet) },
            ...{ class: ("panel") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.select, __VLS_intrinsicElements.select)({
            value: ((__VLS_ctx.taxRuleForm.fiscal_context_id)),
            required: (true),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
            value: (""),
        });
        for (const [row] of __VLS_getVForSourceType((__VLS_ctx.contexts))) {
            __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
                key: ((row.id)),
                value: ((row.id)),
            });
            (row.code);
            (row.establishment_name);
        }
        __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: ("cols") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.input)({
            required: (true),
        });
        (__VLS_ctx.taxRuleForm.code);
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.input)({
            required: (true),
        });
        (__VLS_ctx.taxRuleForm.name);
        __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: ("cols") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.input)({
            placeholder: ("MATRIZ-BA"),
        });
        (__VLS_ctx.taxRuleForm.establishment_code);
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.input)({
            required: (true),
        });
        (__VLS_ctx.taxRuleForm.operation_type);
        __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: ("cols") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.select, __VLS_intrinsicElements.select)({
            value: ((__VLS_ctx.taxRuleForm.item_kind)),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
            value: ("any"),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
            value: ("product"),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
            value: ("service"),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
            value: ("mixed"),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.input)({
            placeholder: ("any"),
        });
        (__VLS_ctx.taxRuleForm.tax_regime);
        __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: ("cols") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.select, __VLS_intrinsicElements.select)({
            value: ((__VLS_ctx.taxRuleForm.rtc_mode)),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
            value: ("any"),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
            value: ("disabled"),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
            value: ("simulation_only"),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
            value: ("optional_emit"),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
            value: ("required_emit"),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.input)({
            type: ("number"),
            min: ("0"),
        });
        (__VLS_ctx.taxRuleForm.priority);
        __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
            ...{ class: ("primary") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.form, __VLS_intrinsicElements.form)({
            ...{ onSubmit: (__VLS_ctx.createTaxRuleVersion) },
            ...{ class: ("panel") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: ("panel-title") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
            ...{ onClick: (__VLS_ctx.addTaxComponent) },
            type: ("button"),
            ...{ class: ("small") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.select, __VLS_intrinsicElements.select)({
            value: ((__VLS_ctx.taxVersionForm.rule_set_id)),
            required: (true),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
            value: (""),
        });
        for (const [row] of __VLS_getVForSourceType((__VLS_ctx.taxRuleSets))) {
            __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
                key: ((row.id)),
                value: ((row.id)),
            });
            (row.code);
            (row.name);
        }
        __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: ("cols") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.input)({
            required: (true),
        });
        (__VLS_ctx.taxVersionForm.version_label);
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.input)({
            type: ("date"),
            required: (true),
        });
        (__VLS_ctx.taxVersionForm.valid_from);
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.input)({
            required: (true),
        });
        (__VLS_ctx.taxVersionForm.source_name);
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.input)({});
        (__VLS_ctx.taxVersionForm.source_reference);
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.textarea, __VLS_intrinsicElements.textarea)({
            value: ((__VLS_ctx.taxVersionForm.legal_basis)),
            rows: ("2"),
        });
        for (const [component, index] of __VLS_getVForSourceType((__VLS_ctx.taxComponents))) {
            __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                key: ((index)),
                ...{ class: ("tax-component") },
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.select, __VLS_intrinsicElements.select)({
                value: ((component.tax)),
            });
            for (const [tax] of __VLS_getVForSourceType((['ICMS', 'ICMS_ST', 'FCP', 'IPI', 'PIS', 'COFINS', 'ISS', 'IBS_ESTADUAL', 'IBS_MUNICIPAL', 'CBS', 'IS']))) {
                __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
                    key: ((tax)),
                    value: ((tax)),
                });
                (tax);
            }
            __VLS_elementAsFunction(__VLS_intrinsicElements.select, __VLS_intrinsicElements.select)({
                value: ((component.incidence)),
            });
            for (const [incidence] of __VLS_getVForSourceType((['taxable', 'exempt', 'deferred', 'suspended', 'immune', 'non_incident', 'zero_rate', 'monophase']))) {
                __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
                    key: ((incidence)),
                    value: ((incidence)),
                });
                (incidence);
            }
            __VLS_elementAsFunction(__VLS_intrinsicElements.select, __VLS_intrinsicElements.select)({
                value: ((component.base_mode)),
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
                value: ("operation_total"),
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
                value: ("mva"),
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.input)({
                type: ("number"),
                step: ("0.0001"),
                min: ("0"),
                placeholder: ("Alíquota %"),
            });
            (component.rate_pct);
            __VLS_elementAsFunction(__VLS_intrinsicElements.input)({
                type: ("number"),
                step: ("0.0001"),
                min: ("0"),
                placeholder: ("Redução %"),
            });
            (component.base_reduction_pct);
            __VLS_elementAsFunction(__VLS_intrinsicElements.input)({
                type: ("number"),
                step: ("0.0001"),
                min: ("0"),
                placeholder: ("Diferimento %"),
            });
            (component.deferral_pct);
            __VLS_elementAsFunction(__VLS_intrinsicElements.input)({
                type: ("number"),
                step: ("0.0001"),
                min: ("0"),
                placeholder: ("Suspensão %"),
            });
            (component.suspension_pct);
            __VLS_elementAsFunction(__VLS_intrinsicElements.input)({
                type: ("number"),
                step: ("0.0001"),
                min: ("0"),
                placeholder: ("MVA %"),
            });
            (component.mva_pct);
            __VLS_elementAsFunction(__VLS_intrinsicElements.input)({
                type: ("number"),
                step: ("0.0001"),
                min: ("0"),
                placeholder: ("Monofásico/unidade"),
            });
            (component.monophase_amount_per_unit);
            __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                ...{ onClick: (...[$event]) => {
                        if (!(!((__VLS_ctx.tab === 'contexts'))))
                            return;
                        if (!(!((__VLS_ctx.tab === 'catalogs'))))
                            return;
                        if (!((__VLS_ctx.tab === 'engine')))
                            return;
                        __VLS_ctx.removeTaxComponent(index);
                    } },
                type: ("button"),
                ...{ class: ("small danger") },
                disabled: ((__VLS_ctx.taxComponents.length === 1)),
            });
        }
        __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
            ...{ class: ("primary") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
            ...{ class: ("grid-2 forms") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.form, __VLS_intrinsicElements.form)({
            ...{ onSubmit: (__VLS_ctx.simulateTaxCalculation) },
            ...{ class: ("panel") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.select, __VLS_intrinsicElements.select)({
            value: ((__VLS_ctx.taxSimulationForm.fiscal_context_id)),
            required: (true),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
            value: (""),
        });
        for (const [row] of __VLS_getVForSourceType((__VLS_ctx.contexts))) {
            __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
                key: ((row.id)),
                value: ((row.id)),
            });
            (row.code);
            (row.establishment_name);
        }
        __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: ("cols") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.input)({});
        (__VLS_ctx.taxSimulationForm.establishment_code);
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.input)({});
        (__VLS_ctx.taxSimulationForm.operation_type);
        __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: ("cols") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.select, __VLS_intrinsicElements.select)({
            value: ((__VLS_ctx.taxSimulationForm.item_kind)),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
            value: ("product"),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
            value: ("service"),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
            value: ("mixed"),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.input)({
            type: ("date"),
        });
        (__VLS_ctx.taxSimulationForm.occurred_on);
        __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: ("cols") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.input)({
            type: ("number"),
            step: ("0.01"),
            min: ("0"),
        });
        (__VLS_ctx.taxSimulationForm.amount);
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.input)({
            type: ("number"),
            step: ("0.0001"),
            min: ("0.0001"),
        });
        (__VLS_ctx.taxSimulationForm.quantity);
        __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: ("cols") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.input)({
            type: ("number"),
            step: ("0.01"),
            min: ("0"),
        });
        (__VLS_ctx.taxSimulationForm.freight);
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.input)({
            type: ("number"),
            step: ("0.01"),
            min: ("0"),
        });
        (__VLS_ctx.taxSimulationForm.insurance);
        __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: ("cols") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.input)({
            type: ("number"),
            step: ("0.01"),
            min: ("0"),
        });
        (__VLS_ctx.taxSimulationForm.other_amount);
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.input)({
            type: ("number"),
            step: ("0.01"),
            min: ("0"),
        });
        (__VLS_ctx.taxSimulationForm.discount);
        __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
            ...{ class: ("primary") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: ("panel") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: ("panel-title") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
        if (__VLS_ctx.taxCalculation) {
            __VLS_elementAsFunction(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
            (__VLS_ctx.taxCalculation.tax_total);
        }
        if (__VLS_ctx.taxCalculation) {
            __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: ("details") },
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.b, __VLS_intrinsicElements.b)({});
            (__VLS_ctx.taxCalculation.rule_set?.code);
            __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.b, __VLS_intrinsicElements.b)({});
            (__VLS_ctx.taxCalculation.rule_set?.version?.version_label);
            __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.b, __VLS_intrinsicElements.b)({});
            (__VLS_ctx.taxCalculation.context?.tax_regime);
            __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.b, __VLS_intrinsicElements.b)({});
            (__VLS_ctx.taxCalculation.context?.rtc_mode);
            __VLS_elementAsFunction(__VLS_intrinsicElements.table, __VLS_intrinsicElements.table)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.thead, __VLS_intrinsicElements.thead)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.tr, __VLS_intrinsicElements.tr)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.th, __VLS_intrinsicElements.th)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.th, __VLS_intrinsicElements.th)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.th, __VLS_intrinsicElements.th)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.th, __VLS_intrinsicElements.th)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.th, __VLS_intrinsicElements.th)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.tbody, __VLS_intrinsicElements.tbody)({});
            for (const [row] of __VLS_getVForSourceType((__VLS_ctx.taxLines))) {
                __VLS_elementAsFunction(__VLS_intrinsicElements.tr, __VLS_intrinsicElements.tr)({
                    key: ((row.tax)),
                });
                __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
                (row.tax);
                __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
                (row.incidence);
                __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
                (row.base);
                __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
                (row.rate_pct);
                __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
                (row.amount);
            }
            __VLS_elementAsFunction(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.b, __VLS_intrinsicElements.b)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.code, __VLS_intrinsicElements.code)({});
            (__VLS_ctx.taxCalculation.snapshot_sha256);
            if (__VLS_ctx.taxCalculation.divergences?.length) {
                __VLS_elementAsFunction(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({
                    ...{ class: ("warn-text") },
                });
                (__VLS_ctx.taxCalculation.divergences.length);
            }
        }
        else {
            __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: ("empty") },
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
        (__VLS_ctx.taxRuleSets.length);
        __VLS_elementAsFunction(__VLS_intrinsicElements.table, __VLS_intrinsicElements.table)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.thead, __VLS_intrinsicElements.thead)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.tr, __VLS_intrinsicElements.tr)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.th, __VLS_intrinsicElements.th)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.th, __VLS_intrinsicElements.th)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.th, __VLS_intrinsicElements.th)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.th, __VLS_intrinsicElements.th)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.th, __VLS_intrinsicElements.th)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.tbody, __VLS_intrinsicElements.tbody)({});
        for (const [row] of __VLS_getVForSourceType((__VLS_ctx.taxRuleSets))) {
            __VLS_elementAsFunction(__VLS_intrinsicElements.tr, __VLS_intrinsicElements.tr)({
                key: ((row.id)),
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
            (row.code);
            __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
            (row.operation_type);
            (row.item_kind);
            (row.establishment_code ?? 'geral');
            __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
            (row.tax_regime);
            __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
            (row.rtc_mode);
            __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
            (row.active_version?.version_label ?? '—');
        }
        if (!__VLS_ctx.taxRuleSets.length) {
            __VLS_elementAsFunction(__VLS_intrinsicElements.tr, __VLS_intrinsicElements.tr)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({
                colspan: ("5"),
                ...{ class: ("empty") },
            });
        }
    }
    else if (__VLS_ctx.tab === 'strategies') {
        __VLS_elementAsFunction(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
            ...{ class: ("grid-2 forms") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.form, __VLS_intrinsicElements.form)({
            ...{ onSubmit: (__VLS_ctx.createLegalSource) },
            ...{ class: ("panel") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: ("cols") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.input)({});
        (__VLS_ctx.legalSourceForm.kind);
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.input)({
            required: (true),
        });
        (__VLS_ctx.legalSourceForm.version_label);
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.input)({
            required: (true),
        });
        (__VLS_ctx.legalSourceForm.title);
        __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: ("cols") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.input)({
            type: ("date"),
        });
        (__VLS_ctx.legalSourceForm.valid_from);
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.input)({
            type: ("date"),
        });
        (__VLS_ctx.legalSourceForm.valid_until);
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.input)({});
        (__VLS_ctx.legalSourceForm.source_reference);
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.input)({});
        (__VLS_ctx.legalSourceForm.source_sha256);
        __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
            ...{ class: ("primary") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.form, __VLS_intrinsicElements.form)({
            ...{ onSubmit: (__VLS_ctx.createRtcSchedule) },
            ...{ class: ("panel") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.select, __VLS_intrinsicElements.select)({
            value: ((__VLS_ctx.rtcForm.fiscal_context_id)),
            required: (true),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
            value: (""),
        });
        for (const [row] of __VLS_getVForSourceType((__VLS_ctx.contexts))) {
            __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
                key: ((row.id)),
                value: ((row.id)),
            });
            (row.code);
        }
        __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: ("cols") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.input)({});
        (__VLS_ctx.rtcForm.tax_regime);
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.select, __VLS_intrinsicElements.select)({
            value: ((__VLS_ctx.rtcForm.mode)),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
            value: ("disabled"),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
            value: ("simulation_only"),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
            value: ("optional_emit"),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
            value: ("required_emit"),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: ("cols") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.input)({
            type: ("date"),
        });
        (__VLS_ctx.rtcForm.valid_from);
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.input)({
            type: ("date"),
        });
        (__VLS_ctx.rtcForm.valid_until);
        __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
            ...{ class: ("primary") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
            ...{ class: ("grid-2 forms") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.form, __VLS_intrinsicElements.form)({
            ...{ onSubmit: (__VLS_ctx.createStrategy) },
            ...{ class: ("panel") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.select, __VLS_intrinsicElements.select)({
            value: ((__VLS_ctx.strategyForm.fiscal_context_id)),
            required: (true),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
            value: (""),
        });
        for (const [row] of __VLS_getVForSourceType((__VLS_ctx.contexts))) {
            __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
                key: ((row.id)),
                value: ((row.id)),
            });
            (row.code);
        }
        __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: ("cols") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.select, __VLS_intrinsicElements.select)({
            value: ((__VLS_ctx.strategyForm.strategy_type)),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
            value: ("withholding"),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
            value: ("difal"),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
            value: ("presumed_credit"),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
            value: ("return"),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
            value: ("transfer"),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
            value: ("adjustment"),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
            value: ("reversal"),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
            value: ("import"),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
            value: ("export"),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
            value: ("specific_regime"),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.input)({});
        (__VLS_ctx.strategyForm.operation_type);
        __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: ("cols") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.input)({
            type: ("number"),
            step: ("0.0001"),
        });
        (__VLS_ctx.strategyForm.rate_pct);
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.input)({
            type: ("number"),
            step: ("0.01"),
        });
        (__VLS_ctx.strategyForm.amount);
        __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
            ...{ class: ("primary") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.form, __VLS_intrinsicElements.form)({
            ...{ onSubmit: (__VLS_ctx.createIbptProfile) },
            ...{ class: ("panel") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: ("cols") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.select, __VLS_intrinsicElements.select)({
            value: ((__VLS_ctx.ibptProfileForm.mode)),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
            value: ("disabled"),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
            value: ("local_snapshot"),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
            value: ("remote_sync"),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.input)({});
        (__VLS_ctx.ibptProfileForm.provider_code);
        __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: ("cols") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.input)({
            type: ("date"),
        });
        (__VLS_ctx.ibptProfileForm.valid_from);
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.input)({
            type: ("date"),
        });
        (__VLS_ctx.ibptProfileForm.valid_until);
        __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: ("cols") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.input)({
            type: ("checkbox"),
        });
        (__VLS_ctx.ibptProfileForm.sync_enabled);
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.input)({
            type: ("checkbox"),
        });
        (__VLS_ctx.ibptProfileForm.fallback_enabled);
        __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: ("cols") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.input)({
            type: ("number"),
            min: ("0"),
        });
        (__VLS_ctx.ibptProfileForm.fallback_max_age_days);
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.input)({
            type: ("number"),
            min: ("0"),
        });
        (__VLS_ctx.ibptProfileForm.stale_after_days);
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.input)({
            placeholder: ("configuração local/secret"),
        });
        (__VLS_ctx.ibptProfileForm.base_url);
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.input)({
            placeholder: ("/tabela/ibpt/{uf}"),
        });
        (__VLS_ctx.ibptProfileForm.uf_path);
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
        (__VLS_ctx.ibptProfiles.length);
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
        for (const [row] of __VLS_getVForSourceType((__VLS_ctx.ibptProfiles))) {
            __VLS_elementAsFunction(__VLS_intrinsicElements.tr, __VLS_intrinsicElements.tr)({
                key: ((row.id)),
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
            (row.version);
            (row.provider_code);
            __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
            (row.mode);
            __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
            (row.sync_enabled ? 'ativo' : 'não');
            __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
            (row.fallback_enabled ? row.fallback_max_age_days + ' dias' : 'desabilitado');
            __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
            (__VLS_ctx.formatDate(row.valid_from));
            (__VLS_ctx.formatDate(row.valid_until));
            __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
            (row.state);
        }
        if (!__VLS_ctx.ibptProfiles.length) {
            __VLS_elementAsFunction(__VLS_intrinsicElements.tr, __VLS_intrinsicElements.tr)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({
                colspan: ("6"),
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
        (__VLS_ctx.ibptStatus?.status ?? '—');
        __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: ("details") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.b, __VLS_intrinsicElements.b)({});
        (__VLS_ctx.ibptUf);
        __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.b, __VLS_intrinsicElements.b)({});
        (__VLS_ctx.ibptSnapshots.length);
        __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.b, __VLS_intrinsicElements.b)({});
        (__VLS_ctx.ibptStatus?.missing_ufs?.length ?? 0);
        __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.b, __VLS_intrinsicElements.b)({});
        (__VLS_ctx.ibptStatus?.quarantine_count ?? 0);
        __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: ("actions") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.select, __VLS_intrinsicElements.select)({
            value: ((__VLS_ctx.ibptUf)),
        });
        for (const [uf] of __VLS_getVForSourceType((['AC', 'AL', 'AP', 'AM', 'BA', 'CE', 'DF', 'ES', 'GO', 'MA', 'MT', 'MS', 'MG', 'PA', 'PB', 'PR', 'PE', 'PI', 'RJ', 'RN', 'RS', 'RO', 'RR', 'SC', 'SP', 'SE', 'TO']))) {
            __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
                key: ((uf)),
            });
            (uf);
        }
        __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
            ...{ onClick: (__VLS_ctx.syncIbpt) },
            type: ("button"),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
            ...{ onClick: (__VLS_ctx.loadIbptOffline) },
            type: ("button"),
        });
        if (__VLS_ctx.ibptOffline) {
            __VLS_elementAsFunction(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.b, __VLS_intrinsicElements.b)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.code, __VLS_intrinsicElements.code)({});
            (__VLS_ctx.ibptOffline.package_sha256);
        }
        __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: ("panel") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.table, __VLS_intrinsicElements.table)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.thead, __VLS_intrinsicElements.thead)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.tr, __VLS_intrinsicElements.tr)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.th, __VLS_intrinsicElements.th)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.th, __VLS_intrinsicElements.th)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.th, __VLS_intrinsicElements.th)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.th, __VLS_intrinsicElements.th)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.th, __VLS_intrinsicElements.th)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.tbody, __VLS_intrinsicElements.tbody)({});
        for (const [row] of __VLS_getVForSourceType((__VLS_ctx.ibptSnapshots.filter(s => !__VLS_ctx.ibptUf || s.uf === __VLS_ctx.ibptUf)))) {
            __VLS_elementAsFunction(__VLS_intrinsicElements.tr, __VLS_intrinsicElements.tr)({
                key: ((row.id)),
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
            (row.uf);
            __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
            (row.source_version);
            __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
            (row.state);
            __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.code, __VLS_intrinsicElements.code)({});
            (row.sha256);
            __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
            if (row.state !== 'active') {
                __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                    ...{ onClick: (...[$event]) => {
                            if (!(!((__VLS_ctx.tab === 'contexts'))))
                                return;
                            if (!(!((__VLS_ctx.tab === 'catalogs'))))
                                return;
                            if (!(!((__VLS_ctx.tab === 'engine'))))
                                return;
                            if (!((__VLS_ctx.tab === 'strategies')))
                                return;
                            if (!((row.state !== 'active')))
                                return;
                            __VLS_ctx.rollbackIbpt(row);
                        } },
                    type: ("button"),
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
        (__VLS_ctx.strategyRules.length);
        __VLS_elementAsFunction(__VLS_intrinsicElements.table, __VLS_intrinsicElements.table)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.thead, __VLS_intrinsicElements.thead)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.tr, __VLS_intrinsicElements.tr)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.th, __VLS_intrinsicElements.th)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.th, __VLS_intrinsicElements.th)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.th, __VLS_intrinsicElements.th)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.th, __VLS_intrinsicElements.th)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.th, __VLS_intrinsicElements.th)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.tbody, __VLS_intrinsicElements.tbody)({});
        for (const [row] of __VLS_getVForSourceType((__VLS_ctx.strategyRules))) {
            __VLS_elementAsFunction(__VLS_intrinsicElements.tr, __VLS_intrinsicElements.tr)({
                key: ((row.id)),
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
            (row.strategy_type);
            __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
            (row.operation_type);
            __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
            (row.tax_regime);
            __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
            (row.rtc_mode);
            __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
            (__VLS_ctx.formatDate(row.valid_from));
        }
    }
    else if (__VLS_ctx.tab === 'routing') {
        __VLS_elementAsFunction(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
            ...{ class: ("grid-2 forms") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.form, __VLS_intrinsicElements.form)({
            ...{ onSubmit: (__VLS_ctx.createDocumentSchema) },
            ...{ class: ("panel grid-form") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: ("cols") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.select, __VLS_intrinsicElements.select)({
            value: ((__VLS_ctx.documentSchemaForm.document_type)),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.input)({
            required: (true),
        });
        (__VLS_ctx.documentSchemaForm.schema_code);
        __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: ("cols") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.input)({
            required: (true),
        });
        (__VLS_ctx.documentSchemaForm.version_label);
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.input)({
            type: ("date"),
        });
        (__VLS_ctx.documentSchemaForm.valid_from);
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.input)({
            required: (true),
        });
        (__VLS_ctx.documentSchemaForm.root_element);
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.input)({});
        (__VLS_ctx.documentSchemaForm.namespace_uri);
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.input)({});
        (__VLS_ctx.documentSchemaForm.source_reference);
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.textarea, __VLS_intrinsicElements.textarea)({
            value: ((__VLS_ctx.documentSchemaForm.xsd_text)),
            rows: ("8"),
            required: (true),
            placeholder: ("Cole o XSD local/versionado"),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
            ...{ class: ("primary") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.form, __VLS_intrinsicElements.form)({
            ...{ onSubmit: (__VLS_ctx.createRoutingPolicy) },
            ...{ class: ("panel grid-form") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.select, __VLS_intrinsicElements.select)({
            value: ((__VLS_ctx.routingPolicyForm.fiscal_context_id)),
            required: (true),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
            value: (""),
        });
        for (const [row] of __VLS_getVForSourceType((__VLS_ctx.contexts))) {
            __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
                key: ((row.id)),
                value: ((row.id)),
            });
            (row.code);
            (row.establishment_name);
        }
        __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: ("cols") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.input)({
            required: (true),
        });
        (__VLS_ctx.routingPolicyForm.code);
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.input)({
            required: (true),
        });
        (__VLS_ctx.routingPolicyForm.name);
        __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: ("cols") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.input)({});
        (__VLS_ctx.routingPolicyForm.operation_type);
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.select, __VLS_intrinsicElements.select)({
            value: ((__VLS_ctx.routingPolicyForm.recipient_scope)),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
            value: ("any"),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
            value: ("individual"),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
            value: ("company"),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
            value: ("government"),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
            value: ("foreign"),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: ("cols") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.input)({});
        (__VLS_ctx.routingPolicyForm.channel_scope);
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.select, __VLS_intrinsicElements.select)({
            value: ((__VLS_ctx.routingPolicyForm.product_document_type)),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
            value: (""),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.select, __VLS_intrinsicElements.select)({
            value: ((__VLS_ctx.routingPolicyForm.trigger_types[0])),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
            value: ("manual"),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
            value: ("sale_completed"),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
            value: ("service_order_confirmed"),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
            value: ("competence"),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
            value: ("payment"),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
            value: ("billing"),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: ("cols") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.input)({
            placeholder: ("simples_nacional"),
        });
        (__VLS_ctx.routingPolicyForm.tax_regime_filter);
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.input)({
            placeholder: ("2927408"),
        });
        (__VLS_ctx.routingPolicyForm.municipality_filter);
        __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: ("cols") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.select, __VLS_intrinsicElements.select)({
            value: ((__VLS_ctx.routingPolicyForm.financial_cancel_mode)),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
            value: ("link_only"),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
            value: ("cancel_unpaid_charge"),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({
            ...{ class: ("check") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.input)({
            type: ("checkbox"),
        });
        (__VLS_ctx.routingPolicyForm.require_financial_contract);
        __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: ("cols") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.input)({
            placeholder: ("configurável pela contabilidade"),
        });
        (__VLS_ctx.routingPolicyForm.fiscal_reversal_debit_account);
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.input)({
            placeholder: ("configurável pela contabilidade"),
        });
        (__VLS_ctx.routingPolicyForm.fiscal_reversal_credit_account);
        __VLS_elementAsFunction(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
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
        (__VLS_ctx.documentSchemas.length);
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
        for (const [row] of __VLS_getVForSourceType((__VLS_ctx.documentSchemas))) {
            __VLS_elementAsFunction(__VLS_intrinsicElements.tr, __VLS_intrinsicElements.tr)({
                key: ((row.id)),
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
            (row.document_type);
            __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
            (row.schema_code);
            __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
            (row.version_label);
            __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
            (__VLS_ctx.formatDate(row.valid_from));
            __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.code, __VLS_intrinsicElements.code)({});
            (row.xsd_sha256);
            __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
            (row.state);
            if (row.state === 'draft') {
                __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                    ...{ onClick: (...[$event]) => {
                            if (!(!((__VLS_ctx.tab === 'contexts'))))
                                return;
                            if (!(!((__VLS_ctx.tab === 'catalogs'))))
                                return;
                            if (!(!((__VLS_ctx.tab === 'engine'))))
                                return;
                            if (!(!((__VLS_ctx.tab === 'strategies'))))
                                return;
                            if (!((__VLS_ctx.tab === 'routing')))
                                return;
                            if (!((row.state === 'draft')))
                                return;
                            __VLS_ctx.publishDocumentSchema(row);
                        } },
                    type: ("button"),
                    ...{ class: ("small") },
                });
            }
        }
        if (!__VLS_ctx.documentSchemas.length) {
            __VLS_elementAsFunction(__VLS_intrinsicElements.tr, __VLS_intrinsicElements.tr)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({
                colspan: ("6"),
                ...{ class: ("empty") },
            });
        }
        __VLS_elementAsFunction(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
            ...{ class: ("grid-2 forms") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.form, __VLS_intrinsicElements.form)({
            ...{ onSubmit: (__VLS_ctx.assembleFiscalDocument) },
            ...{ class: ("panel grid-form") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: ("cols") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.select, __VLS_intrinsicElements.select)({
            value: ((__VLS_ctx.assemblyForm.fiscal_context_id)),
            required: (true),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
            value: (""),
        });
        for (const [row] of __VLS_getVForSourceType((__VLS_ctx.contexts))) {
            __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
                key: ((row.id)),
                value: ((row.id)),
            });
            (row.code);
        }
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.input)({
            required: (true),
        });
        (__VLS_ctx.assemblyForm.fiscal_profile_id);
        __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: ("cols") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.select, __VLS_intrinsicElements.select)({
            value: ((__VLS_ctx.assemblyForm.source_type)),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
            value: ("manual"),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
            value: ("sale"),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
            value: ("service_order"),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.input)({
            required: (true),
        });
        (__VLS_ctx.assemblyForm.source_id);
        __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: ("cols") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.select, __VLS_intrinsicElements.select)({
            value: ((__VLS_ctx.assemblyForm.recipient_scope)),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
            value: ("individual"),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
            value: ("company"),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
            value: ("government"),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
            value: ("foreign"),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.input)({});
        (__VLS_ctx.assemblyForm.channel);
        __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: ("cols") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.input)({});
        (__VLS_ctx.assemblyForm.recipient_name);
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.input)({});
        (__VLS_ctx.assemblyForm.recipient_document);
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.textarea, __VLS_intrinsicElements.textarea)({
            value: ((__VLS_ctx.assemblyForm.items_json)),
            rows: ("9"),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.input)({
            type: ("checkbox"),
        });
        (__VLS_ctx.assemblyForm.request_emission);
        __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
            ...{ class: ("primary") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: ("panel") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
        if (__VLS_ctx.assemblyResult) {
            __VLS_elementAsFunction(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.b, __VLS_intrinsicElements.b)({});
            (__VLS_ctx.assemblyResult.state);
            __VLS_elementAsFunction(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.b, __VLS_intrinsicElements.b)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.code, __VLS_intrinsicElements.code)({});
            (__VLS_ctx.assemblyResult.input_sha256);
            __VLS_elementAsFunction(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.b, __VLS_intrinsicElements.b)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.code, __VLS_intrinsicElements.code)({});
            (__VLS_ctx.assemblyResult.output_sha256);
            for (const [build] of __VLS_getVForSourceType((__VLS_ctx.assemblyResult.builds ?? []))) {
                __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                    key: ((build.id)),
                    ...{ class: ("version-list") },
                });
                __VLS_elementAsFunction(__VLS_intrinsicElements.article, __VLS_intrinsicElements.article)({});
                __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({});
                __VLS_elementAsFunction(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
                (build.document_type);
                (build.relationship);
                __VLS_elementAsFunction(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
                (build.validation_state);
                (build.item_count);
                __VLS_elementAsFunction(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
                (build.routing_reasons?.join(', '));
            }
        }
        else {
            __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: ("empty") },
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
        (__VLS_ctx.fiscalAssemblies.length);
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
        for (const [row] of __VLS_getVForSourceType((__VLS_ctx.fiscalAssemblies))) {
            __VLS_elementAsFunction(__VLS_intrinsicElements.tr, __VLS_intrinsicElements.tr)({
                key: ((row.id)),
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
            (row.source_type);
            (row.source_id);
            __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
            (row.operation_type);
            (row.channel);
            __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
            (row.trigger_type);
            __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
            (row.state);
            __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.code, __VLS_intrinsicElements.code)({});
            (row.input_sha256);
            __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.code, __VLS_intrinsicElements.code)({});
            (row.output_sha256 ?? '—');
        }
        if (!__VLS_ctx.fiscalAssemblies.length) {
            __VLS_elementAsFunction(__VLS_intrinsicElements.tr, __VLS_intrinsicElements.tr)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({
                colspan: ("6"),
                ...{ class: ("empty") },
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
        (__VLS_ctx.emissionTriggerRuns.length);
        __VLS_elementAsFunction(__VLS_intrinsicElements.table, __VLS_intrinsicElements.table)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.thead, __VLS_intrinsicElements.thead)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.tr, __VLS_intrinsicElements.tr)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.th, __VLS_intrinsicElements.th)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.th, __VLS_intrinsicElements.th)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.th, __VLS_intrinsicElements.th)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.th, __VLS_intrinsicElements.th)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.tbody, __VLS_intrinsicElements.tbody)({});
        for (const [row] of __VLS_getVForSourceType((__VLS_ctx.emissionTriggerRuns))) {
            __VLS_elementAsFunction(__VLS_intrinsicElements.tr, __VLS_intrinsicElements.tr)({
                key: ((row.id)),
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
            (row.event_type);
            __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
            (row.source_type);
            (row.source_id);
            __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
            (row.state);
            __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                ...{ onClick: (...[$event]) => {
                        if (!(!((__VLS_ctx.tab === 'contexts'))))
                            return;
                        if (!(!((__VLS_ctx.tab === 'catalogs'))))
                            return;
                        if (!(!((__VLS_ctx.tab === 'engine'))))
                            return;
                        if (!(!((__VLS_ctx.tab === 'strategies'))))
                            return;
                        if (!((__VLS_ctx.tab === 'routing')))
                            return;
                        __VLS_ctx.evaluateEmissionTrigger(row);
                    } },
                type: ("button"),
                ...{ class: ("small") },
            });
        }
        if (!__VLS_ctx.emissionTriggerRuns.length) {
            __VLS_elementAsFunction(__VLS_intrinsicElements.tr, __VLS_intrinsicElements.tr)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({
                colspan: ("4"),
                ...{ class: ("empty") },
            });
        }
    }
    else if (__VLS_ctx.tab === 'documents') {
        __VLS_elementAsFunction(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
            ...{ class: ("panel") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: ("panel-title") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
        (__VLS_ctx.fiscalProviders.length);
        __VLS_elementAsFunction(__VLS_intrinsicElements.form, __VLS_intrinsicElements.form)({
            ...{ onSubmit: (__VLS_ctx.createFiscalProvider) },
            ...{ class: ("grid-form") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: ("cols") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.select, __VLS_intrinsicElements.select)({
            value: ((__VLS_ctx.providerForm.provider_code)),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.select, __VLS_intrinsicElements.select)({
            value: ((__VLS_ctx.providerForm.document_type)),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.input)({
            required: (true),
        });
        (__VLS_ctx.providerForm.display_name);
        __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: ("cols") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.input)({
            placeholder: ("https://..."),
        });
        (__VLS_ctx.providerForm.endpoint_url);
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.input)({
            placeholder: ("nome-no-secret-store"),
        });
        (__VLS_ctx.providerForm.secret_ref);
        __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: ("cols") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.select, __VLS_intrinsicElements.select)({
            value: ((__VLS_ctx.providerForm.certificate_metadata_id)),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
            value: (""),
        });
        for (const [row] of __VLS_getVForSourceType((__VLS_ctx.fiscalCertificates))) {
            __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
                key: ((row.id)),
                value: ((row.id)),
            });
            (row.subject_name);
            (row.valid_until);
        }
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.select, __VLS_intrinsicElements.select)({
            value: ((__VLS_ctx.providerForm.environment)),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
            value: ("homologation"),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
            value: ("production"),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.input)({
            type: ("checkbox"),
        });
        (__VLS_ctx.providerForm.enabled);
        __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
            ...{ class: ("primary") },
        });
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
        for (const [row] of __VLS_getVForSourceType((__VLS_ctx.fiscalProviders))) {
            __VLS_elementAsFunction(__VLS_intrinsicElements.tr, __VLS_intrinsicElements.tr)({
                key: ((row.id)),
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
            (row.display_name);
            __VLS_elementAsFunction(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
            (row.provider_code);
            __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
            (row.document_type);
            __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
            (row.environment);
            __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
            (row.status);
            __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
            (row.last_health_status);
            __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                ...{ onClick: (...[$event]) => {
                        if (!(!((__VLS_ctx.tab === 'contexts'))))
                            return;
                        if (!(!((__VLS_ctx.tab === 'catalogs'))))
                            return;
                        if (!(!((__VLS_ctx.tab === 'engine'))))
                            return;
                        if (!(!((__VLS_ctx.tab === 'strategies'))))
                            return;
                        if (!(!((__VLS_ctx.tab === 'routing'))))
                            return;
                        if (!((__VLS_ctx.tab === 'documents')))
                            return;
                        __VLS_ctx.checkFiscalProvider(row);
                    } },
                type: ("button"),
            });
        }
        if (!__VLS_ctx.fiscalProviders.length) {
            __VLS_elementAsFunction(__VLS_intrinsicElements.tr, __VLS_intrinsicElements.tr)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({
                colspan: ("6"),
                ...{ class: ("empty") },
            });
        }
        __VLS_elementAsFunction(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
            ...{ class: ("split") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.form, __VLS_intrinsicElements.form)({
            ...{ onSubmit: (__VLS_ctx.createFiscalCertificate) },
            ...{ class: ("panel grid-form") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.input)({
            required: (true),
        });
        (__VLS_ctx.certificateForm.subject_name);
        __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: ("cols") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.input)({});
        (__VLS_ctx.certificateForm.subject_document);
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.input)({
            required: (true),
        });
        (__VLS_ctx.certificateForm.serial_number);
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.input)({
            required: (true),
        });
        (__VLS_ctx.certificateForm.issuer_name);
        __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: ("cols") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.input)({});
        (__VLS_ctx.certificateForm.valid_from);
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.input)({});
        (__VLS_ctx.certificateForm.valid_until);
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.input)({
            minlength: ("64"),
            maxlength: ("64"),
            required: (true),
        });
        (__VLS_ctx.certificateForm.fingerprint_sha256);
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.input)({
            required: (true),
        });
        (__VLS_ctx.certificateForm.secret_ref);
        __VLS_elementAsFunction(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
            ...{ class: ("primary") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.form, __VLS_intrinsicElements.form)({
            ...{ onSubmit: (__VLS_ctx.createFiscalInutilization) },
            ...{ class: ("panel grid-form") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.input)({
            required: (true),
        });
        (__VLS_ctx.inutilizationForm.fiscal_profile_id);
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.select, __VLS_intrinsicElements.select)({
            value: ((__VLS_ctx.inutilizationForm.provider_configuration_id)),
            required: (true),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
            value: (""),
        });
        for (const [row] of __VLS_getVForSourceType((__VLS_ctx.fiscalProviders.filter(p => p.document_type === __VLS_ctx.inutilizationForm.document_type)))) {
            __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
                key: ((row.id)),
                value: ((row.id)),
            });
            (row.display_name);
        }
        __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: ("cols") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.select, __VLS_intrinsicElements.select)({
            value: ((__VLS_ctx.inutilizationForm.document_type)),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.input)({
            type: ("number"),
        });
        (__VLS_ctx.inutilizationForm.year);
        __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: ("cols") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.input)({});
        (__VLS_ctx.inutilizationForm.series);
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.input)({
            type: ("number"),
            min: ("1"),
        });
        (__VLS_ctx.inutilizationForm.start_number);
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.input)({
            type: ("number"),
            min: ("1"),
        });
        (__VLS_ctx.inutilizationForm.end_number);
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.textarea)({
            value: ((__VLS_ctx.inutilizationForm.reason)),
            minlength: ("15"),
            required: (true),
        });
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
        (__VLS_ctx.deliveryPolicies.length);
        __VLS_elementAsFunction(__VLS_intrinsicElements.form, __VLS_intrinsicElements.form)({
            ...{ onSubmit: (__VLS_ctx.createDeliveryPolicy) },
            ...{ class: ("grid-form") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: ("cols") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.input)({
            required: (true),
        });
        (__VLS_ctx.deliveryPolicyForm.code);
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.input)({
            required: (true),
        });
        (__VLS_ctx.deliveryPolicyForm.name);
        __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: ("cols") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.select, __VLS_intrinsicElements.select)({
            value: ((__VLS_ctx.deliveryPolicyForm.document_type)),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
            value: ("any"),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.select, __VLS_intrinsicElements.select)({
            value: ((__VLS_ctx.deliveryPolicyForm.provider_code)),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
            value: (""),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.select, __VLS_intrinsicElements.select)({
            value: ((__VLS_ctx.deliveryPolicyForm.environment)),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
            value: ("any"),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
            value: ("homologation"),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
            value: ("production"),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: ("cols") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.input)({
            type: ("number"),
            min: ("1"),
            max: ("30"),
        });
        (__VLS_ctx.deliveryPolicyForm.max_attempts);
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.input)({
            type: ("number"),
            min: ("0"),
        });
        (__VLS_ctx.deliveryPolicyForm.base_delay_seconds);
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.input)({
            type: ("number"),
            min: ("0"),
        });
        (__VLS_ctx.deliveryPolicyForm.max_delay_seconds);
        __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: ("cols") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.input)({});
        (__VLS_ctx.deliveryPolicyForm.backoff_multiplier);
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.input)({
            type: ("number"),
            min: ("1"),
        });
        (__VLS_ctx.deliveryPolicyForm.contingency_after_attempts);
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.select, __VLS_intrinsicElements.select)({
            value: ((__VLS_ctx.deliveryPolicyForm.contingency_mode)),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
            value: ("offline"),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
            value: ("svc"),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
            value: ("epec"),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.input)({
            type: ("checkbox"),
        });
        (__VLS_ctx.deliveryPolicyForm.auto_retry);
        __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
            ...{ class: ("primary") },
        });
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
        for (const [row] of __VLS_getVForSourceType((__VLS_ctx.deliveryPolicies))) {
            __VLS_elementAsFunction(__VLS_intrinsicElements.tr, __VLS_intrinsicElements.tr)({
                key: ((row.id)),
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
            (row.code);
            __VLS_elementAsFunction(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
            (row.version);
            __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
            (row.document_type);
            __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
            (row.provider_code ?? 'qualquer');
            __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
            (row.max_attempts);
            __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
            (row.base_delay_seconds);
            (row.max_delay_seconds);
            __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
            (row.contingency_after_attempts ? `${row.contingency_after_attempts} · ${row.contingency_mode}` : '—');
            __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
            (row.state);
        }
        if (!__VLS_ctx.deliveryPolicies.length) {
            __VLS_elementAsFunction(__VLS_intrinsicElements.tr, __VLS_intrinsicElements.tr)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({
                colspan: ("7"),
                ...{ class: ("empty") },
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
        (__VLS_ctx.documents.length);
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
        for (const [row] of __VLS_getVForSourceType((__VLS_ctx.documents))) {
            __VLS_elementAsFunction(__VLS_intrinsicElements.tr, __VLS_intrinsicElements.tr)({
                key: ((row.id)),
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
            (row.document_type);
            __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
            (row.source_type);
            (row.source_id);
            __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
            (row.provider_status);
            __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({
                ...{ class: ("pill") },
                ...{ class: ((row.state === 'authorized' ? 'ok' : row.state.includes('awaiting') ? 'warn' : '')) },
            });
            (row.state);
            __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
            (row.contingency_mode ?? '—');
            __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({
                ...{ class: ("actions") },
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                ...{ onClick: (...[$event]) => {
                        if (!(!((__VLS_ctx.tab === 'contexts'))))
                            return;
                        if (!(!((__VLS_ctx.tab === 'catalogs'))))
                            return;
                        if (!(!((__VLS_ctx.tab === 'engine'))))
                            return;
                        if (!(!((__VLS_ctx.tab === 'strategies'))))
                            return;
                        if (!(!((__VLS_ctx.tab === 'routing'))))
                            return;
                        if (!((__VLS_ctx.tab === 'documents')))
                            return;
                        __VLS_ctx.queryFiscalDocument(row);
                    } },
                type: ("button"),
            });
            if (row.state === 'authorized') {
                __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                    ...{ onClick: (...[$event]) => {
                            if (!(!((__VLS_ctx.tab === 'contexts'))))
                                return;
                            if (!(!((__VLS_ctx.tab === 'catalogs'))))
                                return;
                            if (!(!((__VLS_ctx.tab === 'engine'))))
                                return;
                            if (!(!((__VLS_ctx.tab === 'strategies'))))
                                return;
                            if (!(!((__VLS_ctx.tab === 'routing'))))
                                return;
                            if (!((__VLS_ctx.tab === 'documents')))
                                return;
                            if (!((row.state === 'authorized')))
                                return;
                            __VLS_ctx.requestCorrectionEvent(row);
                        } },
                    type: ("button"),
                });
            }
            if (row.state === 'authorized') {
                __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                    ...{ onClick: (...[$event]) => {
                            if (!(!((__VLS_ctx.tab === 'contexts'))))
                                return;
                            if (!(!((__VLS_ctx.tab === 'catalogs'))))
                                return;
                            if (!(!((__VLS_ctx.tab === 'engine'))))
                                return;
                            if (!(!((__VLS_ctx.tab === 'strategies'))))
                                return;
                            if (!(!((__VLS_ctx.tab === 'routing'))))
                                return;
                            if (!((__VLS_ctx.tab === 'documents')))
                                return;
                            if (!((row.state === 'authorized')))
                                return;
                            __VLS_ctx.substituteFiscalDocument(row);
                        } },
                    type: ("button"),
                });
            }
            __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                ...{ onClick: (...[$event]) => {
                        if (!(!((__VLS_ctx.tab === 'contexts'))))
                            return;
                        if (!(!((__VLS_ctx.tab === 'catalogs'))))
                            return;
                        if (!(!((__VLS_ctx.tab === 'engine'))))
                            return;
                        if (!(!((__VLS_ctx.tab === 'strategies'))))
                            return;
                        if (!(!((__VLS_ctx.tab === 'routing'))))
                            return;
                        if (!((__VLS_ctx.tab === 'documents')))
                            return;
                        __VLS_ctx.renderFiscalDocument(row);
                    } },
                type: ("button"),
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                ...{ onClick: (...[$event]) => {
                        if (!(!((__VLS_ctx.tab === 'contexts'))))
                            return;
                        if (!(!((__VLS_ctx.tab === 'catalogs'))))
                            return;
                        if (!(!((__VLS_ctx.tab === 'engine'))))
                            return;
                        if (!(!((__VLS_ctx.tab === 'strategies'))))
                            return;
                        if (!(!((__VLS_ctx.tab === 'routing'))))
                            return;
                        if (!((__VLS_ctx.tab === 'documents')))
                            return;
                        __VLS_ctx.loadDocumentArtifacts(row);
                    } },
                type: ("button"),
            });
            if (['rejected', 'requested'].includes(String(row.state))) {
                __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                    ...{ onClick: (...[$event]) => {
                            if (!(!((__VLS_ctx.tab === 'contexts'))))
                                return;
                            if (!(!((__VLS_ctx.tab === 'catalogs'))))
                                return;
                            if (!(!((__VLS_ctx.tab === 'engine'))))
                                return;
                            if (!(!((__VLS_ctx.tab === 'strategies'))))
                                return;
                            if (!(!((__VLS_ctx.tab === 'routing'))))
                                return;
                            if (!((__VLS_ctx.tab === 'documents')))
                                return;
                            if (!((['rejected', 'requested'].includes(String(row.state)))))
                                return;
                            __VLS_ctx.retryFiscalDocument(row);
                        } },
                    type: ("button"),
                });
            }
            if (row.error_code || row.state === 'rejected') {
                __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                    ...{ onClick: (...[$event]) => {
                            if (!(!((__VLS_ctx.tab === 'contexts'))))
                                return;
                            if (!(!((__VLS_ctx.tab === 'catalogs'))))
                                return;
                            if (!(!((__VLS_ctx.tab === 'engine'))))
                                return;
                            if (!(!((__VLS_ctx.tab === 'strategies'))))
                                return;
                            if (!(!((__VLS_ctx.tab === 'routing'))))
                                return;
                            if (!((__VLS_ctx.tab === 'documents')))
                                return;
                            if (!((row.error_code || row.state === 'rejected')))
                                return;
                            __VLS_ctx.loadFiscalRejection(row);
                        } },
                    type: ("button"),
                });
            }
            __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                ...{ onClick: (...[$event]) => {
                        if (!(!((__VLS_ctx.tab === 'contexts'))))
                            return;
                        if (!(!((__VLS_ctx.tab === 'catalogs'))))
                            return;
                        if (!(!((__VLS_ctx.tab === 'engine'))))
                            return;
                        if (!(!((__VLS_ctx.tab === 'strategies'))))
                            return;
                        if (!(!((__VLS_ctx.tab === 'routing'))))
                            return;
                        if (!((__VLS_ctx.tab === 'documents')))
                            return;
                        __VLS_ctx.loadDocumentTransparency(row);
                    } },
                type: ("button"),
            });
            if (row.state === 'authorized') {
                __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                    ...{ onClick: (...[$event]) => {
                            if (!(!((__VLS_ctx.tab === 'contexts'))))
                                return;
                            if (!(!((__VLS_ctx.tab === 'catalogs'))))
                                return;
                            if (!(!((__VLS_ctx.tab === 'engine'))))
                                return;
                            if (!(!((__VLS_ctx.tab === 'strategies'))))
                                return;
                            if (!(!((__VLS_ctx.tab === 'routing'))))
                                return;
                            if (!((__VLS_ctx.tab === 'documents')))
                                return;
                            if (!((row.state === 'authorized')))
                                return;
                            __VLS_ctx.cancelFiscalDocument(row);
                        } },
                    type: ("button"),
                    ...{ class: ("danger") },
                });
            }
        }
        if (!__VLS_ctx.documents.length) {
            __VLS_elementAsFunction(__VLS_intrinsicElements.tr, __VLS_intrinsicElements.tr)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({
                colspan: ("6"),
                ...{ class: ("empty") },
            });
        }
        if (__VLS_ctx.selectedArtifactDocument) {
            __VLS_elementAsFunction(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
                ...{ class: ("panel") },
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: ("panel-title") },
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
            (__VLS_ctx.selectedArtifactDocument.document_type);
            __VLS_elementAsFunction(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
            (__VLS_ctx.selectedArtifactDocument.id);
            __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                ...{ onClick: (...[$event]) => {
                        if (!(!((__VLS_ctx.tab === 'contexts'))))
                            return;
                        if (!(!((__VLS_ctx.tab === 'catalogs'))))
                            return;
                        if (!(!((__VLS_ctx.tab === 'engine'))))
                            return;
                        if (!(!((__VLS_ctx.tab === 'strategies'))))
                            return;
                        if (!(!((__VLS_ctx.tab === 'routing'))))
                            return;
                        if (!((__VLS_ctx.tab === 'documents')))
                            return;
                        if (!((__VLS_ctx.selectedArtifactDocument)))
                            return;
                        __VLS_ctx.selectedArtifactDocument = null;
                        __VLS_ctx.selectedArtifacts = [];
                    } },
                type: ("button"),
                ...{ class: ("small") },
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.table, __VLS_intrinsicElements.table)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.thead, __VLS_intrinsicElements.thead)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.tr, __VLS_intrinsicElements.tr)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.th, __VLS_intrinsicElements.th)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.th, __VLS_intrinsicElements.th)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.th, __VLS_intrinsicElements.th)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.th, __VLS_intrinsicElements.th)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.th, __VLS_intrinsicElements.th)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.tbody, __VLS_intrinsicElements.tbody)({});
            for (const [artifact] of __VLS_getVForSourceType((__VLS_ctx.selectedArtifacts))) {
                __VLS_elementAsFunction(__VLS_intrinsicElements.tr, __VLS_intrinsicElements.tr)({
                    key: ((artifact.id)),
                });
                __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
                (artifact.artifact_type);
                __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
                __VLS_elementAsFunction(__VLS_intrinsicElements.code, __VLS_intrinsicElements.code)({});
                (artifact.sha256);
                __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
                (artifact.bytes_count);
                __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
                __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({
                    ...{ class: ("pill") },
                    ...{ class: ((artifact.available ? 'ok' : 'warn')) },
                });
                (artifact.available ? 'sim' : 'não');
                __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
                if (artifact.available) {
                    __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                        ...{ onClick: (...[$event]) => {
                                if (!(!((__VLS_ctx.tab === 'contexts'))))
                                    return;
                                if (!(!((__VLS_ctx.tab === 'catalogs'))))
                                    return;
                                if (!(!((__VLS_ctx.tab === 'engine'))))
                                    return;
                                if (!(!((__VLS_ctx.tab === 'strategies'))))
                                    return;
                                if (!(!((__VLS_ctx.tab === 'routing'))))
                                    return;
                                if (!((__VLS_ctx.tab === 'documents')))
                                    return;
                                if (!((__VLS_ctx.selectedArtifactDocument)))
                                    return;
                                if (!((artifact.available)))
                                    return;
                                __VLS_ctx.downloadFiscalArtifact(__VLS_ctx.selectedArtifactDocument, artifact);
                            } },
                        type: ("button"),
                        ...{ class: ("small") },
                    });
                }
            }
            if (!__VLS_ctx.selectedArtifacts.length) {
                __VLS_elementAsFunction(__VLS_intrinsicElements.tr, __VLS_intrinsicElements.tr)({});
                __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({
                    colspan: ("5"),
                    ...{ class: ("empty") },
                });
            }
        }
        if (__VLS_ctx.selectedRejection) {
            __VLS_elementAsFunction(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
                ...{ class: ("panel") },
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: ("panel-title") },
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
            (__VLS_ctx.selectedRejection.state);
            if (__VLS_ctx.selectedRejection.rejection) {
                __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                    ...{ class: ("details") },
                });
                __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
                __VLS_elementAsFunction(__VLS_intrinsicElements.b, __VLS_intrinsicElements.b)({});
                (__VLS_ctx.selectedRejection.rejection.error_code ?? '—');
                __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
                __VLS_elementAsFunction(__VLS_intrinsicElements.b, __VLS_intrinsicElements.b)({});
                (__VLS_ctx.selectedRejection.rejection.category);
                __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
                __VLS_elementAsFunction(__VLS_intrinsicElements.b, __VLS_intrinsicElements.b)({});
                (__VLS_ctx.selectedRejection.rejection.retryable ? 'sim' : 'não');
                __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
                __VLS_elementAsFunction(__VLS_intrinsicElements.b, __VLS_intrinsicElements.b)({});
                (__VLS_ctx.selectedRejection.rejection.next_retry_at ?? '—');
            }
            if (__VLS_ctx.selectedRejection.rejection) {
                __VLS_elementAsFunction(__VLS_intrinsicElements.pre, __VLS_intrinsicElements.pre)({});
                (JSON.stringify(__VLS_ctx.selectedRejection.rejection.explanation, null, 2));
            }
            else {
                __VLS_elementAsFunction(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({});
            }
        }
        if (__VLS_ctx.documentTransparency) {
            __VLS_elementAsFunction(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
                ...{ class: ("panel") },
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: ("panel-title") },
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
            (__VLS_ctx.documentTransparency.vtottrib ?? '0.00');
            __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: ("details") },
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.b, __VLS_intrinsicElements.b)({});
            (__VLS_ctx.documentTransparency.fiscal_document_id);
            __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.b, __VLS_intrinsicElements.b)({});
            (__VLS_ctx.documentTransparency.ibpt_provider_profile_id ?? 'cache local legado');
            __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.b, __VLS_intrinsicElements.b)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.b, __VLS_intrinsicElements.b)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: ("grid-2") },
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.h3, __VLS_intrinsicElements.h3)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.pre, __VLS_intrinsicElements.pre)({});
            (JSON.stringify(__VLS_ctx.documentTransparency.real_taxes, null, 2));
            __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.h3, __VLS_intrinsicElements.h3)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.pre, __VLS_intrinsicElements.pre)({});
            (JSON.stringify(__VLS_ctx.documentTransparency.approximate_ibpt, null, 2));
            __VLS_elementAsFunction(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.b, __VLS_intrinsicElements.b)({});
        }
        __VLS_elementAsFunction(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
            ...{ class: ("panel") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: ("panel-title") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
        (__VLS_ctx.fiscalInutilizations.length);
        __VLS_elementAsFunction(__VLS_intrinsicElements.table, __VLS_intrinsicElements.table)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.thead, __VLS_intrinsicElements.thead)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.tr, __VLS_intrinsicElements.tr)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.th, __VLS_intrinsicElements.th)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.th, __VLS_intrinsicElements.th)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.th, __VLS_intrinsicElements.th)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.th, __VLS_intrinsicElements.th)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.th, __VLS_intrinsicElements.th)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.tbody, __VLS_intrinsicElements.tbody)({});
        for (const [row] of __VLS_getVForSourceType((__VLS_ctx.fiscalInutilizations))) {
            __VLS_elementAsFunction(__VLS_intrinsicElements.tr, __VLS_intrinsicElements.tr)({
                key: ((row.id)),
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
            (row.document_type);
            __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
            (row.series);
            (row.start_number);
            (row.end_number);
            __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
            (row.year);
            __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
            (row.state);
            __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
            (row.protocol ?? '—');
        }
        if (!__VLS_ctx.fiscalInutilizations.length) {
            __VLS_elementAsFunction(__VLS_intrinsicElements.tr, __VLS_intrinsicElements.tr)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({
                colspan: ("5"),
                ...{ class: ("empty") },
            });
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
        (__VLS_ctx.rules.length);
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
        for (const [row] of __VLS_getVForSourceType((__VLS_ctx.rules))) {
            __VLS_elementAsFunction(__VLS_intrinsicElements.tr, __VLS_intrinsicElements.tr)({
                key: ((row.id)),
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.code, __VLS_intrinsicElements.code)({});
            (row.fiscal_profile_id);
            __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
            (row.operation_type);
            __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
            (row.item_kind);
            __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
            (row.classification_key ?? "geral");
            __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
            (__VLS_ctx.formatDate(row.effective_from));
            (__VLS_ctx.formatDate(row.effective_until));
            __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
            (row.version);
        }
        if (!__VLS_ctx.rules.length) {
            __VLS_elementAsFunction(__VLS_intrinsicElements.tr, __VLS_intrinsicElements.tr)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({
                colspan: ("6"),
                ...{ class: ("empty") },
            });
        }
    }
    ['fiscal-panel', 'metrics', 'tabs', 'panel', 'active', 'active', 'active', 'active', 'active', 'active', 'active', 'small', 'refresh', 'grid-2', 'forms', 'panel', 'cols', 'cols', 'cols', 'primary', 'panel', 'panel-title', 'context-list', 'selected', 'pill', 'empty', 'panel', 'panel-title', 'actions', 'small', 'small', 'small', 'danger', 'small', 'details', 'grid-2', 'forms', 'panel', 'cols', 'cols', 'cols', 'cols', 'cols', 'scope-title', 'small', 'scope-row', 'small', 'danger', 'primary', 'panel', 'panel-title', 'version-list', 'pill', 'small', 'empty', 'grid-2', 'forms', 'panel', 'cols', 'cols', 'primary', 'panel', 'empty', 'grid-2', 'forms', 'panel', 'cols', 'cols', 'primary', 'panel', 'cols', 'cols', 'primary', 'grid-2', 'forms', 'panel', 'cols', 'cols', 'cols', 'classification-grid', 'actions', 'primary', 'small', 'panel', 'panel-title', 'details', 'pill', 'empty', 'grid-2', 'forms', 'panel', 'cols', 'cols', 'primary', 'panel', 'cols', 'inline-check', 'primary', 'panel', 'panel-title', 'pill', 'warn-text', 'grid-2', 'panel', 'panel-title', 'small', 'small', 'empty', 'panel', 'panel-title', 'small', 'danger', 'empty', 'panel', 'panel-title', 'empty', 'panel', 'panel-title', 'grid-2', 'forms', 'panel', 'cols', 'cols', 'cols', 'cols', 'primary', 'panel', 'panel-title', 'small', 'cols', 'tax-component', 'small', 'danger', 'primary', 'grid-2', 'forms', 'panel', 'cols', 'cols', 'cols', 'cols', 'cols', 'primary', 'panel', 'panel-title', 'details', 'warn-text', 'empty', 'panel', 'panel-title', 'empty', 'grid-2', 'forms', 'panel', 'cols', 'cols', 'primary', 'panel', 'cols', 'cols', 'primary', 'grid-2', 'forms', 'panel', 'cols', 'cols', 'primary', 'panel', 'cols', 'cols', 'cols', 'cols', 'primary', 'panel', 'panel-title', 'empty', 'grid-2', 'panel', 'panel-title', 'details', 'actions', 'panel', 'small', 'panel', 'panel-title', 'grid-2', 'forms', 'panel', 'grid-form', 'cols', 'cols', 'primary', 'panel', 'grid-form', 'cols', 'cols', 'cols', 'cols', 'cols', 'check', 'cols', 'primary', 'panel', 'panel-title', 'small', 'empty', 'grid-2', 'forms', 'panel', 'grid-form', 'cols', 'cols', 'cols', 'cols', 'primary', 'panel', 'version-list', 'empty', 'panel', 'panel-title', 'empty', 'panel', 'panel-title', 'small', 'empty', 'panel', 'panel-title', 'grid-form', 'cols', 'cols', 'cols', 'primary', 'empty', 'split', 'panel', 'grid-form', 'cols', 'cols', 'primary', 'panel', 'grid-form', 'cols', 'cols', 'primary', 'panel', 'panel-title', 'grid-form', 'cols', 'cols', 'cols', 'cols', 'primary', 'empty', 'panel', 'panel-title', 'pill', 'actions', 'danger', 'empty', 'panel', 'panel-title', 'small', 'pill', 'small', 'empty', 'panel', 'panel-title', 'details', 'panel', 'panel-title', 'details', 'grid-2', 'panel', 'panel-title', 'empty', 'panel', 'panel-title', 'empty',];
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
            contexts: contexts,
            documents: documents,
            fiscalProviders: fiscalProviders,
            fiscalCertificates: fiscalCertificates,
            fiscalInutilizations: fiscalInutilizations,
            documentSchemas: documentSchemas,
            fiscalAssemblies: fiscalAssemblies,
            emissionTriggerRuns: emissionTriggerRuns,
            rules: rules,
            catalogs: catalogs,
            catalogImports: catalogImports,
            catalogGovernance: catalogGovernance,
            catalogQuarantine: catalogQuarantine,
            catalogImportFile: catalogImportFile,
            classificationRules: classificationRules,
            taxRuleSets: taxRuleSets,
            taxCalculation: taxCalculation,
            taxLines: taxLines,
            strategyRules: strategyRules,
            ibptStatus: ibptStatus,
            ibptSnapshots: ibptSnapshots,
            ibptOffline: ibptOffline,
            ibptProfiles: ibptProfiles,
            documentTransparency: documentTransparency,
            deliveryPolicies: deliveryPolicies,
            selectedRejection: selectedRejection,
            selectedArtifactDocument: selectedArtifactDocument,
            selectedArtifacts: selectedArtifacts,
            readiness: readiness,
            institutions: institutions,
            selectedContext: selectedContext,
            resolved: resolved,
            contextForm: contextForm,
            versionForm: versionForm,
            scopes: scopes,
            resolveForm: resolveForm,
            catalogForm: catalogForm,
            catalogVersionForm: catalogVersionForm,
            catalogSourceForm: catalogSourceForm,
            catalogImportForm: catalogImportForm,
            classificationForm: classificationForm,
            taxRuleForm: taxRuleForm,
            taxVersionForm: taxVersionForm,
            taxComponents: taxComponents,
            taxSimulationForm: taxSimulationForm,
            legalSourceForm: legalSourceForm,
            strategyForm: strategyForm,
            rtcForm: rtcForm,
            ibptUf: ibptUf,
            ibptProfileForm: ibptProfileForm,
            certificateForm: certificateForm,
            providerForm: providerForm,
            deliveryPolicyForm: deliveryPolicyForm,
            inutilizationForm: inutilizationForm,
            documentSchemaForm: documentSchemaForm,
            routingPolicyForm: routingPolicyForm,
            assemblyForm: assemblyForm,
            assemblyResult: assemblyResult,
            fiscalConnections: fiscalConnections,
            publishedVersions: publishedVersions,
            awaitingProvider: awaitingProvider,
            filteredUnits: filteredUnits,
            importSources: importSources,
            formatDate: formatDate,
            contextStatus: contextStatus,
            sourceProfilesLabel: sourceProfilesLabel,
            selectCatalogImportFile: selectCatalogImportFile,
            load: load,
            createContext: createContext,
            showContext: showContext,
            updateContextStatus: updateContextStatus,
            addScope: addScope,
            removeScope: removeScope,
            createVersion: createVersion,
            publishVersion: publishVersion,
            resolveCurrent: resolveCurrent,
            createCatalog: createCatalog,
            createCatalogVersion: createCatalogVersion,
            createCatalogSource: createCatalogSource,
            importCatalogFile: importCatalogFile,
            publishCatalogImport: publishCatalogImport,
            rollbackCatalogImport: rollbackCatalogImport,
            resolveCatalogQuarantine: resolveCatalogQuarantine,
            createClassification: createClassification,
            calculateReadiness: calculateReadiness,
            addTaxComponent: addTaxComponent,
            removeTaxComponent: removeTaxComponent,
            createTaxRuleSet: createTaxRuleSet,
            createTaxRuleVersion: createTaxRuleVersion,
            simulateTaxCalculation: simulateTaxCalculation,
            createLegalSource: createLegalSource,
            createStrategy: createStrategy,
            createRtcSchedule: createRtcSchedule,
            syncIbpt: syncIbpt,
            loadIbptOffline: loadIbptOffline,
            rollbackIbpt: rollbackIbpt,
            createIbptProfile: createIbptProfile,
            loadDocumentTransparency: loadDocumentTransparency,
            createFiscalCertificate: createFiscalCertificate,
            createFiscalProvider: createFiscalProvider,
            checkFiscalProvider: checkFiscalProvider,
            createDeliveryPolicy: createDeliveryPolicy,
            retryFiscalDocument: retryFiscalDocument,
            renderFiscalDocument: renderFiscalDocument,
            loadDocumentArtifacts: loadDocumentArtifacts,
            downloadFiscalArtifact: downloadFiscalArtifact,
            loadFiscalRejection: loadFiscalRejection,
            queryFiscalDocument: queryFiscalDocument,
            cancelFiscalDocument: cancelFiscalDocument,
            substituteFiscalDocument: substituteFiscalDocument,
            requestCorrectionEvent: requestCorrectionEvent,
            createFiscalInutilization: createFiscalInutilization,
            createDocumentSchema: createDocumentSchema,
            publishDocumentSchema: publishDocumentSchema,
            createRoutingPolicy: createRoutingPolicy,
            assembleFiscalDocument: assembleFiscalDocument,
            evaluateEmissionTrigger: evaluateEmissionTrigger,
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
