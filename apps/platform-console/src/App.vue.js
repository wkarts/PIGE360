import { onMounted, reactive, ref } from "vue";
import { Pige360SessionClient } from "@pige360/auth";
import CommercialAdministrationPanel from "./components/CommercialAdministrationPanel.vue";
import OperationalAdministrationPanel from "./components/OperationalAdministrationPanel.vue";
const api = new Pige360SessionClient();
const ready = ref(false);
const auth = ref(false);
const busy = ref(false);
const error = ref("");
const notice = ref("");
const email = ref("");
const password = ref("");
const tenants = ref([]);
const status = ref({});
const audit = ref([]);
const support = ref([]);
const inventory = ref({});
const platformUsers = ref([]);
const selected = ref(null);
const apps = ref({ entitlements: [], manifests: [], builds: [], releases: [] });
const branding = ref({});
const domains = ref([]);
const quotas = ref({ configured: {}, effective: {}, enforcement: {} });
const logs = ref([]);
const lastLogQuery = ref("");
const form = reactive({ code: "", legal_name: "", trade_name: "", owner_email: "", owner_password: "" });
const supportForm = reactive({ reason: "", ticket: "", minutes: 30 });
const supportEndReason = ref("");
const lifecycleReason = ref("");
const quotaReason = ref("");
const domainForm = reactive({ hostname: "", surface: "admin" });
const logFilters = reactive({ correlation_id: "", service: "", plane: "", level: "", minutes: 60, limit: 200 });
const quotaForm = reactive({
    max_users: 500,
    max_students: 5000,
    storage_bytes: 107374182400,
    api_requests_per_minute: 6000,
    max_integrations: 20,
    max_concurrent_builds: 2,
    max_custom_domains: 10,
});
const selectedProducts = ref(["pwa"]);
const selectedPlatforms = ref(["pwa"]);
const productOptions = [
    ["pwa", "Web / PWA"],
    ["family-mobile", "Família mobile"],
    ["teacher-mobile", "Professor mobile"],
    ["student-mobile", "Aluno mobile"],
    ["admin-mobile", "Admin mobile"],
    ["pos-mobile", "PDV mobile"],
    ["kiosk", "Quiosque"],
    ["timeclock", "Ponto"],
    ["desktop-admin", "Admin desktop"],
    ["pos-desktop", "PDV desktop"],
];
const platformOptions = [
    ["pwa", "PWA"],
    ["android-apk", "Android APK"],
    ["android-aab", "Android AAB"],
    ["ios-app", "iOS App"],
    ["ios-xcarchive", "iOS Archive"],
    ["ios-ipa-unsigned", "iOS IPA sem assinatura"],
    ["windows-x64", "Windows x64"],
    ["windows-x86", "Windows x86"],
    ["linux-x64", "Linux x64"],
    ["linux-arm64", "Linux ARM64"],
    ["macos-intel", "macOS Intel"],
    ["macos-apple", "macOS Apple"],
];
function msg(e) {
    const p = e?.problem;
    return p?.detail || (e instanceof Error ? e.message : "Erro inesperado");
}
function clearFeedback() {
    error.value = "";
    notice.value = "";
}
function handlePanelFeedback(value) {
    clearFeedback();
    if (value.type === "success")
        notice.value = value.message;
    else
        error.value = value.message;
}
function canonicalDomainHost() {
    return String(domains.value.find((domain) => Boolean(domain.is_canonical) && domain.status === "active")?.hostname || "—");
}
function selectedSupportSessions() {
    return support.value.filter((session) => session.tenant_id === selected.value?.id);
}
function canManagePlatformUsers() {
    return Boolean(api.claims()?.roles?.includes("platform_super_admin"));
}
async function load() {
    clearFeedback();
    const [t, s, a, ss, operations, users] = await Promise.all([
        api.request("/platform/tenants"),
        api.request("/platform/status"),
        api.request("/platform/audit?limit=50"),
        api.request("/platform/support-sessions?active_only=true"),
        api.request("/platform/operations/inventory"),
        api.request("/platform/users"),
    ]);
    tenants.value = t.items || [];
    status.value = s;
    audit.value = a.items || [];
    support.value = ss.items || [];
    inventory.value = operations;
    platformUsers.value = users.items || [];
    if (selected.value) {
        const fresh = tenants.value.find((x) => x.id === selected.value?.id);
        if (fresh)
            selected.value = fresh;
        await loadTenant();
    }
}
async function loadTenant() {
    if (!selected.value)
        return;
    const [appData, brandData, domainData, quotaData] = await Promise.all([
        api.request(`/platform/tenants/${selected.value.id}/apps`),
        api.request(`/platform/tenants/${selected.value.id}/branding`),
        api.request(`/platform/tenants/${selected.value.id}/domains`),
        api.request(`/platform/tenants/${selected.value.id}/quotas`),
    ]);
    apps.value = appData;
    branding.value = brandData;
    domains.value = domainData.items || [];
    quotas.value = quotaData;
    Object.assign(quotaForm, quotaData.effective || {});
}
async function boot() {
    try {
        await api.initialize();
        auth.value = !!api.tokens;
        if (auth.value)
            await load();
    }
    catch (e) {
        error.value = msg(e);
    }
    finally {
        ready.value = true;
    }
}
async function login() {
    clearFeedback();
    try {
        await api.login(email.value, password.value);
        if (api.claims()?.plane !== "platform")
            throw new Error("Use uma conta do Control Plane.");
        auth.value = true;
        await load();
    }
    catch (e) {
        error.value = msg(e);
    }
}
async function logout() {
    await api.logout();
    auth.value = false;
}
async function createTenant() {
    busy.value = true;
    clearFeedback();
    try {
        const created = await api.request("/platform/tenants", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(form),
        });
        notice.value = `Tenant provisionado em ${created.hostname}.`;
        Object.assign(form, { code: "", legal_name: "", trade_name: "", owner_email: "", owner_password: "" });
        await load();
    }
    catch (e) {
        error.value = msg(e);
    }
    finally {
        busy.value = false;
    }
}
async function choose(t) {
    selected.value = t;
    logs.value = [];
    await loadTenant();
}
async function createSupport() {
    if (!selected.value)
        return;
    clearFeedback();
    try {
        await api.request(`/platform/tenants/${selected.value.id}/support-sessions`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(supportForm),
        });
        notice.value = "Sessão de suporte auditada criada.";
        await load();
    }
    catch (e) {
        error.value = msg(e);
    }
}
async function revokeSupport(session) {
    if (!supportEndReason.value.trim()) {
        error.value = "Informe o motivo do encerramento da sessão de suporte.";
        return;
    }
    clearFeedback();
    try {
        await api.request(`/platform/support-sessions/${session.id}/revoke`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ reason: supportEndReason.value }),
        });
        supportEndReason.value = "";
        notice.value = "Sessão de suporte encerrada e revogada.";
        await load();
    }
    catch (e) {
        error.value = msg(e);
    }
}
async function changeTenantState(action) {
    if (!selected.value)
        return;
    if (!lifecycleReason.value.trim()) {
        error.value = "Informe um motivo auditável para alterar o status do tenant.";
        return;
    }
    clearFeedback();
    try {
        await api.request(`/platform/tenants/${selected.value.id}/${action}`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ expected_version: selected.value.version, reason: lifecycleReason.value }),
        });
        lifecycleReason.value = "";
        notice.value = action === "suspend" ? "Tenant suspenso." : "Tenant reativado.";
        await load();
    }
    catch (e) {
        error.value = msg(e);
    }
}
async function updateQuotas() {
    if (!selected.value)
        return;
    if (!quotaReason.value.trim()) {
        error.value = "Informe o motivo da alteração das quotas.";
        return;
    }
    clearFeedback();
    try {
        await api.request(`/platform/tenants/${selected.value.id}/quotas`, {
            method: "PUT",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ expected_version: selected.value.version, reason: quotaReason.value, quotas: quotaForm }),
        });
        quotaReason.value = "";
        notice.value = "Quotas atualizadas com controle de versão.";
        await load();
    }
    catch (e) {
        error.value = msg(e);
    }
}
async function setPlatformUserState(platformUser, active) {
    if (!canManagePlatformUsers())
        return;
    const reason = window.prompt(active ? "Motivo para reativar este usuário:" : "Motivo para desativar este usuário:");
    if (!reason)
        return;
    clearFeedback();
    try {
        await api.request(`/platform/users/${platformUser.id}/active`, {
            method: "PATCH",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ active, reason }),
        });
        notice.value = active ? "Usuário da plataforma reativado." : "Usuário da plataforma desativado e sessões revogadas.";
        await load();
    }
    catch (e) {
        error.value = msg(e);
    }
}
async function activateEntitlements() {
    if (!selected.value || busy.value)
        return;
    if (!selectedProducts.value.length) {
        error.value = "Selecione ao menos um produto.";
        return;
    }
    busy.value = true;
    clearFeedback();
    try {
        await Promise.all(selectedProducts.value.map((appProduct) => api.request(`/platform/tenants/${selected.value.id}/apps/entitlements`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ app_product: appProduct, state: "active", contract_reference: "platform-console" }),
        })));
        notice.value = "Entitlements selecionados foram ativados.";
        await loadTenant();
    }
    catch (e) {
        error.value = msg(e);
    }
    finally {
        busy.value = false;
    }
}
async function manifestAndBuild() {
    if (!selected.value || busy.value)
        return;
    if (!selectedProducts.value.length || !selectedPlatforms.value.length) {
        error.value = "Selecione ao menos um produto e uma plataforma.";
        return;
    }
    const brandVersion = branding.value.active_version;
    if (!brandVersion) {
        error.value = "Publique o branding do tenant antes de solicitar builds.";
        return;
    }
    const domain = domains.value.find((d) => d.is_canonical && d.status === "active")?.hostname || domains.value.find((d) => d.status === "active")?.hostname;
    if (!domain) {
        error.value = "Tenant sem domínio provisionado.";
        return;
    }
    const slug = selected.value.code.replace(/[^a-z0-9]/g, "");
    const manifestApps = Object.fromEntries(selectedProducts.value.map((product) => {
        const suffix = product.replace(/[^a-z0-9]/g, "");
        const label = productOptions.find(([value]) => value === product)?.[1] || product;
        const previous = apps.value.manifests?.[0]?.payload?.apps?.[product] || {};
        return [product, {
                enabled: true,
                display_name: `${selected.value.trade_name} ${label}`,
                identifier: previous.identifier || `br.com.${slug}.${suffix}`,
                api_url: `https://${domain}`,
                web_url: `https://${domain}`,
                update_url: `https://${domain}/apps`,
                icon_asset_id: previous.icon_asset_id || null,
                splash_asset_id: previous.splash_asset_id || null,
                features: { finance: true, attendance: true },
                signing: previous.signing?.requires_reconfiguration ? {} : (previous.signing || {}),
            }];
    }));
    busy.value = true;
    clearFeedback();
    try {
        const mf = await api.request(`/platform/tenants/${selected.value.id}/apps/manifests`, {
            method: "POST",
            headers: { "Content-Type": "application/json", "Idempotency-Key": `manifest-${crypto.randomUUID()}` },
            body: JSON.stringify({
                tenant_code: selected.value.code,
                brand_version: brandVersion,
                release_channel: "stable",
                apps: manifestApps,
                metadata: { created_from: "platform-console" },
            }),
        });
        const build = await api.request(`/platform/tenants/${selected.value.id}/apps/builds`, {
            method: "POST",
            headers: { "Content-Type": "application/json", "Idempotency-Key": `build-${crypto.randomUUID()}` },
            body: JSON.stringify({ manifest_id: mf.id, platforms: selectedPlatforms.value, products: selectedProducts.value }),
        });
        notice.value = `Build ${build.build_id} enfileirado com ${build.jobs?.length || 0} jobs compatíveis.`;
        await loadTenant();
    }
    catch (e) {
        error.value = msg(e);
    }
    finally {
        busy.value = false;
    }
}
async function retryBuild(build) {
    if (!selected.value)
        return;
    const reason = window.prompt("Motivo para reenfileirar os jobs com falha:");
    if (!reason)
        return;
    clearFeedback();
    try {
        await api.request(`/platform/tenants/${selected.value.id}/apps/builds/${build.build_id}/retry`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ reason }),
        });
        notice.value = `Build ${build.build_id} reenfileirado.`;
        await loadTenant();
    }
    catch (e) {
        error.value = msg(e);
    }
}
async function createDomain() {
    if (!selected.value)
        return;
    clearFeedback();
    try {
        await api.request(`/platform/tenants/${selected.value.id}/domains`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(domainForm),
        });
        Object.assign(domainForm, { hostname: "", surface: "admin" });
        notice.value = "Domínio cadastrado. Configure CNAME/flattening e TXT antes de verificar.";
        await loadTenant();
    }
    catch (e) {
        error.value = msg(e);
    }
}
async function verifyDomain(domain) {
    if (!selected.value)
        return;
    clearFeedback();
    try {
        await api.request(`/platform/tenants/${selected.value.id}/domains/${domain.id}/verify`, { method: "POST" });
        notice.value = "Propriedade do domínio verificada. TLS foi solicitado.";
        await loadTenant();
    }
    catch (e) {
        error.value = msg(e);
    }
}
async function refreshDomain(domain) {
    if (!selected.value)
        return;
    clearFeedback();
    try {
        const result = await api.request(`/platform/tenants/${selected.value.id}/domains/${domain.id}/refresh`, { method: "POST" });
        notice.value = result.status === "active" ? "Domínio e TLS ativos." : "TLS ainda em provisionamento.";
        await loadTenant();
    }
    catch (e) {
        error.value = msg(e);
    }
}
async function disableDomain(domain) {
    if (!selected.value || domain.is_canonical)
        return;
    clearFeedback();
    try {
        await api.request(`/platform/tenants/${selected.value.id}/domains/${domain.id}`, { method: "DELETE" });
        notice.value = "Domínio personalizado desativado.";
        await loadTenant();
    }
    catch (e) {
        error.value = msg(e);
    }
}
async function copy(value) {
    try {
        await navigator.clipboard.writeText(value);
        notice.value = "Valor copiado.";
    }
    catch {
        error.value = "Não foi possível copiar automaticamente.";
    }
}
async function loadLogs() {
    clearFeedback();
    const params = new URLSearchParams();
    if (selected.value?.id)
        params.set("tenant_id", selected.value.id);
    if (logFilters.correlation_id)
        params.set("correlation_id", logFilters.correlation_id);
    if (logFilters.service)
        params.set("service", logFilters.service);
    if (logFilters.plane)
        params.set("plane", logFilters.plane);
    if (logFilters.level)
        params.set("level", logFilters.level);
    params.set("minutes", String(logFilters.minutes));
    params.set("limit", String(logFilters.limit));
    try {
        const result = await api.request(`/platform/logs?${params.toString()}`);
        logs.value = result.items || [];
        lastLogQuery.value = result.query || "";
    }
    catch (e) {
        error.value = msg(e);
    }
}
onMounted(boot);
; /* PartiallyEnd: #3632/scriptSetup.vue */
function __VLS_template() {
    const __VLS_ctx = {};
    let __VLS_components;
    let __VLS_directives;
    if (!__VLS_ctx.ready) {
        __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: ("center") },
        });
    }
    else if (!__VLS_ctx.auth) {
        __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: ("login-page platform-login") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.form, __VLS_intrinsicElements.form)({
            ...{ onSubmit: (__VLS_ctx.login) },
            ...{ class: ("login-card") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: ("mark") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({
            ...{ class: ("eyebrow") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.h1, __VLS_intrinsicElements.h1)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.input, __VLS_intrinsicElements.input)({
            type: ("email"),
            required: (true),
        });
        (__VLS_ctx.email);
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.input, __VLS_intrinsicElements.input)({
            type: ("password"),
            required: (true),
        });
        (__VLS_ctx.password);
        if (__VLS_ctx.error) {
            __VLS_elementAsFunction(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({
                ...{ class: ("flash error") },
            });
            (__VLS_ctx.error);
        }
        __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
            ...{ class: ("primary") },
        });
    }
    else {
        __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: ("console") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.aside, __VLS_intrinsicElements.aside)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: ("brand") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: ("mark") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
            ...{ onClick: (...[$event]) => {
                    if (!(!((!__VLS_ctx.ready))))
                        return;
                    if (!(!((!__VLS_ctx.auth))))
                        return;
                    __VLS_ctx.selected = null;
                    __VLS_ctx.logs = [];
                } },
            ...{ class: (({ active: !__VLS_ctx.selected })) },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
        for (const [t] of __VLS_getVForSourceType((__VLS_ctx.tenants))) {
            __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                ...{ onClick: (...[$event]) => {
                        if (!(!((!__VLS_ctx.ready))))
                            return;
                        if (!(!((!__VLS_ctx.auth))))
                            return;
                        __VLS_ctx.choose(t);
                    } },
                key: ((t.id)),
                ...{ class: (({ active: __VLS_ctx.selected?.id === t.id })) },
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
            (t.trade_name);
            __VLS_elementAsFunction(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
            (t.status);
        }
        __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
            ...{ onClick: (__VLS_ctx.logout) },
            ...{ class: ("logout") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.main, __VLS_intrinsicElements.main)({});
        if (__VLS_ctx.error) {
            __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: ("flash error") },
            });
            (__VLS_ctx.error);
        }
        if (__VLS_ctx.notice) {
            __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: ("flash success") },
            });
            (__VLS_ctx.notice);
        }
        __VLS_elementAsFunction(__VLS_intrinsicElements.header, __VLS_intrinsicElements.header)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({
            ...{ class: ("eyebrow") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.h1, __VLS_intrinsicElements.h1)({});
        (__VLS_ctx.selected ? __VLS_ctx.selected.trade_name : 'Visão global');
        __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
            ...{ onClick: (__VLS_ctx.load) },
            ...{ class: ("ghost-dark") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
            ...{ class: ("metrics") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.article, __VLS_intrinsicElements.article)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
        (__VLS_ctx.status.tenants?.total || 0);
        __VLS_elementAsFunction(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
        (__VLS_ctx.status.tenants?.active || 0);
        __VLS_elementAsFunction(__VLS_intrinsicElements.article, __VLS_intrinsicElements.article)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
        (__VLS_ctx.status.domains || 0);
        __VLS_elementAsFunction(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.article, __VLS_intrinsicElements.article)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
        (__VLS_ctx.status.builds?.queued || 0);
        __VLS_elementAsFunction(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
        (__VLS_ctx.status.builds?.building || 0);
        __VLS_elementAsFunction(__VLS_intrinsicElements.article, __VLS_intrinsicElements.article)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
        (__VLS_ctx.status.active_support_sessions || 0);
        __VLS_elementAsFunction(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
        if (!__VLS_ctx.selected) {
            __VLS_elementAsFunction(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
                ...{ class: ("grid two") },
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.form, __VLS_intrinsicElements.form)({
                ...{ onSubmit: (__VLS_ctx.createTenant) },
                ...{ class: ("panel form") },
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({
                ...{ class: ("helper") },
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.code, __VLS_intrinsicElements.code)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.input, __VLS_intrinsicElements.input)({
                pattern: ("[a-z0-9-]+"),
                required: (true),
                placeholder: ("colegio-modelo"),
            });
            (__VLS_ctx.form.code);
            __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.input, __VLS_intrinsicElements.input)({
                required: (true),
            });
            (__VLS_ctx.form.legal_name);
            __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.input, __VLS_intrinsicElements.input)({
                required: (true),
            });
            (__VLS_ctx.form.trade_name);
            __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.input, __VLS_intrinsicElements.input)({
                type: ("email"),
                required: (true),
            });
            (__VLS_ctx.form.owner_email);
            __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.input, __VLS_intrinsicElements.input)({
                type: ("password"),
                minlength: ("10"),
                required: (true),
            });
            (__VLS_ctx.form.owner_password);
            __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                ...{ class: ("primary") },
                disabled: ((__VLS_ctx.busy)),
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: ("panel") },
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
            for (const [a] of __VLS_getVForSourceType((__VLS_ctx.audit.slice(0, 15)))) {
                __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                    ...{ class: ("list-row") },
                    key: ((a.id)),
                });
                __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({});
                __VLS_elementAsFunction(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
                (a.action);
                (a.aggregate_type);
                __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
                (a.tenant_id || 'platform');
                (a.correlation_id);
                __VLS_elementAsFunction(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
                (a.created_at);
            }
            __VLS_elementAsFunction(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
                ...{ class: ("grid two") },
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: ("panel") },
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: ("section-title") },
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({
                ...{ class: ("status-pill") },
            });
            (__VLS_ctx.inventory.status || '—');
            __VLS_elementAsFunction(__VLS_intrinsicElements.dl, __VLS_intrinsicElements.dl)({
                ...{ class: ("facts") },
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.dt, __VLS_intrinsicElements.dt)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.dd, __VLS_intrinsicElements.dd)({});
            (__VLS_ctx.inventory.control_database?.provider);
            (__VLS_ctx.inventory.control_database?.state);
            __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.dt, __VLS_intrinsicElements.dt)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.dd, __VLS_intrinsicElements.dd)({});
            (__VLS_ctx.inventory.tenant_resources?.database_reachable || 0);
            (__VLS_ctx.inventory.tenant_resources?.database_unavailable || 0);
            __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.dt, __VLS_intrinsicElements.dt)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.dd, __VLS_intrinsicElements.dd)({});
            (__VLS_ctx.inventory.tenant_resources?.storage_configured || 0);
            __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.dt, __VLS_intrinsicElements.dt)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.dd, __VLS_intrinsicElements.dd)({});
            (__VLS_ctx.inventory.workloads?.control_outbox_pending || 0);
            (__VLS_ctx.inventory.workloads?.tenant_outbox_pending || 0);
            __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.dt, __VLS_intrinsicElements.dt)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.dd, __VLS_intrinsicElements.dd)({});
            (__VLS_ctx.inventory.workloads?.integration_connections || 0);
            __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.dt, __VLS_intrinsicElements.dt)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.dd, __VLS_intrinsicElements.dd)({});
            (__VLS_ctx.inventory.configuration?.mail?.mode || 'disabled');
            (__VLS_ctx.inventory.workloads?.mail_accounts || 0);
            __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.dt, __VLS_intrinsicElements.dt)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.dd, __VLS_intrinsicElements.dd)({});
            (__VLS_ctx.inventory.configuration?.remote_operations?.deploy_enabled ? 'habilitado' : 'desabilitado');
            __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: ("panel") },
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: ("section-title") },
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
            (__VLS_ctx.platformUsers.length);
            for (const [platformUser] of __VLS_getVForSourceType((__VLS_ctx.platformUsers))) {
                __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                    ...{ class: ("list-row") },
                    key: ((platformUser.id)),
                });
                __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({});
                __VLS_elementAsFunction(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
                (platformUser.email);
                __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
                (platformUser.roles.join(', '));
                (platformUser.active ? 'ativo' : 'inativo');
                if (platformUser.is_current_user) {
                }
                if (__VLS_ctx.canManagePlatformUsers() && !platformUser.is_current_user) {
                    __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                        ...{ onClick: (...[$event]) => {
                                if (!(!((!__VLS_ctx.ready))))
                                    return;
                                if (!(!((!__VLS_ctx.auth))))
                                    return;
                                if (!((!__VLS_ctx.selected)))
                                    return;
                                if (!((__VLS_ctx.canManagePlatformUsers() && !platformUser.is_current_user)))
                                    return;
                                __VLS_ctx.setPlatformUserState(platformUser, !platformUser.active);
                            } },
                        ...{ class: ((platformUser.active ? 'danger-outline' : 'ghost-dark')) },
                    });
                    (platformUser.active ? 'Desativar' : 'Reativar');
                }
            }
            if (__VLS_ctx.support.length) {
                __VLS_elementAsFunction(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
                    ...{ class: ("panel") },
                });
                __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                    ...{ class: ("section-title") },
                });
                __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({});
                __VLS_elementAsFunction(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
                __VLS_elementAsFunction(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
                __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
                (__VLS_ctx.support.length);
                for (const [session] of __VLS_getVForSourceType((__VLS_ctx.support))) {
                    __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                        ...{ class: ("list-row") },
                        key: ((session.id)),
                    });
                    __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({});
                    __VLS_elementAsFunction(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
                    (session.ticket || session.id);
                    __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
                    (session.tenant_id);
                    (session.expires_at);
                    __VLS_elementAsFunction(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
                    (session.reason);
                }
            }
            // @ts-ignore
            /** @type { [typeof OperationalAdministrationPanel, ] } */ ;
            // @ts-ignore
            const __VLS_0 = __VLS_asFunctionalComponent(OperationalAdministrationPanel, new OperationalAdministrationPanel({
                ...{ 'onFeedback': {} },
                api: ((__VLS_ctx.api)),
                tenants: ((__VLS_ctx.tenants)),
            }));
            const __VLS_1 = __VLS_0({
                ...{ 'onFeedback': {} },
                api: ((__VLS_ctx.api)),
                tenants: ((__VLS_ctx.tenants)),
            }, ...__VLS_functionalComponentArgsRest(__VLS_0));
            let __VLS_5;
            const __VLS_6 = {
                onFeedback: (__VLS_ctx.handlePanelFeedback)
            };
            let __VLS_2;
            let __VLS_3;
            var __VLS_4;
            // @ts-ignore
            /** @type { [typeof CommercialAdministrationPanel, ] } */ ;
            // @ts-ignore
            const __VLS_7 = __VLS_asFunctionalComponent(CommercialAdministrationPanel, new CommercialAdministrationPanel({
                ...{ 'onFeedback': {} },
                api: ((__VLS_ctx.api)),
                tenants: ((__VLS_ctx.tenants)),
            }));
            const __VLS_8 = __VLS_7({
                ...{ 'onFeedback': {} },
                api: ((__VLS_ctx.api)),
                tenants: ((__VLS_ctx.tenants)),
            }, ...__VLS_functionalComponentArgsRest(__VLS_7));
            let __VLS_12;
            const __VLS_13 = {
                onFeedback: (__VLS_ctx.handlePanelFeedback)
            };
            let __VLS_9;
            let __VLS_10;
            var __VLS_11;
        }
        else {
            __VLS_elementAsFunction(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
                ...{ class: ("grid two") },
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: ("panel form") },
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.dl, __VLS_intrinsicElements.dl)({
                ...{ class: ("facts") },
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.dt, __VLS_intrinsicElements.dt)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.dd, __VLS_intrinsicElements.dd)({});
            (__VLS_ctx.selected.code);
            __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.dt, __VLS_intrinsicElements.dt)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.dd, __VLS_intrinsicElements.dd)({});
            (__VLS_ctx.selected.status);
            __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.dt, __VLS_intrinsicElements.dt)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.dd, __VLS_intrinsicElements.dd)({});
            (__VLS_ctx.selected.version);
            __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.dt, __VLS_intrinsicElements.dt)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.dd, __VLS_intrinsicElements.dd)({});
            (__VLS_ctx.branding.active_version || 0);
            (__VLS_ctx.branding.state);
            __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.dt, __VLS_intrinsicElements.dt)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.dd, __VLS_intrinsicElements.dd)({});
            (__VLS_ctx.canonicalDomainHost());
            __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.textarea, __VLS_intrinsicElements.textarea)({
                value: ((__VLS_ctx.lifecycleReason)),
                minlength: ("10"),
                maxlength: ("2000"),
                placeholder: ("Motivo auditável"),
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: ("row-actions") },
            });
            if (__VLS_ctx.selected.status === 'active' || __VLS_ctx.selected.status === 'degraded') {
                __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                    ...{ onClick: (...[$event]) => {
                            if (!(!((!__VLS_ctx.ready))))
                                return;
                            if (!(!((!__VLS_ctx.auth))))
                                return;
                            if (!(!((!__VLS_ctx.selected))))
                                return;
                            if (!((__VLS_ctx.selected.status === 'active' || __VLS_ctx.selected.status === 'degraded')))
                                return;
                            __VLS_ctx.changeTenantState('suspend');
                        } },
                    ...{ class: ("danger-outline") },
                });
            }
            if (__VLS_ctx.selected.status === 'suspended') {
                __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                    ...{ onClick: (...[$event]) => {
                            if (!(!((!__VLS_ctx.ready))))
                                return;
                            if (!(!((!__VLS_ctx.auth))))
                                return;
                            if (!(!((!__VLS_ctx.selected))))
                                return;
                            if (!((__VLS_ctx.selected.status === 'suspended')))
                                return;
                            __VLS_ctx.changeTenantState('reactivate');
                        } },
                    ...{ class: ("primary") },
                });
            }
            __VLS_elementAsFunction(__VLS_intrinsicElements.form, __VLS_intrinsicElements.form)({
                ...{ onSubmit: (__VLS_ctx.createSupport) },
                ...{ class: ("panel form") },
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.textarea, __VLS_intrinsicElements.textarea)({
                value: ((__VLS_ctx.supportForm.reason)),
                minlength: ("10"),
                required: (true),
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.input, __VLS_intrinsicElements.input)({});
            (__VLS_ctx.supportForm.ticket);
            __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.input, __VLS_intrinsicElements.input)({
                type: ("number"),
                min: ("5"),
                max: ("120"),
            });
            (__VLS_ctx.supportForm.minutes);
            __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                ...{ class: ("primary") },
                disabled: ((__VLS_ctx.selected.status !== 'active')),
            });
            if (__VLS_ctx.selectedSupportSessions().length) {
                __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
                __VLS_elementAsFunction(__VLS_intrinsicElements.input, __VLS_intrinsicElements.input)({
                    minlength: ("10"),
                    placeholder: ("Conclusão do atendimento"),
                });
                (__VLS_ctx.supportEndReason);
                for (const [session] of __VLS_getVForSourceType((__VLS_ctx.selectedSupportSessions()))) {
                    __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                        ...{ class: ("support-session") },
                        key: ((session.id)),
                    });
                    __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({});
                    __VLS_elementAsFunction(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
                    (session.ticket || session.id);
                    __VLS_elementAsFunction(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
                    (session.expires_at);
                    __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                        ...{ onClick: (...[$event]) => {
                                if (!(!((!__VLS_ctx.ready))))
                                    return;
                                if (!(!((!__VLS_ctx.auth))))
                                    return;
                                if (!(!((!__VLS_ctx.selected))))
                                    return;
                                if (!((__VLS_ctx.selectedSupportSessions().length)))
                                    return;
                                __VLS_ctx.revokeSupport(session);
                            } },
                        type: ("button"),
                        ...{ class: ("danger-outline") },
                    });
                }
            }
            __VLS_elementAsFunction(__VLS_intrinsicElements.form, __VLS_intrinsicElements.form)({
                ...{ onSubmit: (__VLS_ctx.updateQuotas) },
                ...{ class: ("panel form") },
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: ("section-title") },
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
            (__VLS_ctx.quotas.version);
            __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
            (Object.keys(__VLS_ctx.quotas.configured || {}).length);
            __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: ("quota-grid") },
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.input, __VLS_intrinsicElements.input)({
                type: ("number"),
                min: ("1"),
                max: ("1000000"),
                required: (true),
            });
            (__VLS_ctx.quotaForm.max_users);
            __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.input, __VLS_intrinsicElements.input)({
                type: ("number"),
                min: ("0"),
                max: ("10000000"),
                required: (true),
            });
            (__VLS_ctx.quotaForm.max_students);
            __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.input, __VLS_intrinsicElements.input)({
                type: ("number"),
                min: ("1048576"),
                required: (true),
            });
            (__VLS_ctx.quotaForm.storage_bytes);
            __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.input, __VLS_intrinsicElements.input)({
                type: ("number"),
                min: ("1"),
                max: ("1000000"),
                required: (true),
            });
            (__VLS_ctx.quotaForm.api_requests_per_minute);
            __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.input, __VLS_intrinsicElements.input)({
                type: ("number"),
                min: ("0"),
                max: ("10000"),
                required: (true),
            });
            (__VLS_ctx.quotaForm.max_integrations);
            __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.input, __VLS_intrinsicElements.input)({
                type: ("number"),
                min: ("1"),
                max: ("64"),
                required: (true),
            });
            (__VLS_ctx.quotaForm.max_concurrent_builds);
            __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.input, __VLS_intrinsicElements.input)({
                type: ("number"),
                min: ("0"),
                max: ("1000"),
                required: (true),
            });
            (__VLS_ctx.quotaForm.max_custom_domains);
            __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: ("entitlements") },
            });
            for (const [rule, key] of __VLS_getVForSourceType((__VLS_ctx.quotas.enforcement))) {
                __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({
                    key: ((String(key))),
                    ...{ class: ("status-pill") },
                });
                (key);
                (rule.status === 'enforced' ? 'aplicada' : 'não aplicada');
            }
            __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.input, __VLS_intrinsicElements.input)({
                minlength: ("10"),
                maxlength: ("2000"),
                required: (true),
            });
            (__VLS_ctx.quotaReason);
            __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                ...{ class: ("primary") },
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
                ...{ class: ("panel") },
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: ("section-title") },
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
            (__VLS_ctx.domains.length);
            __VLS_elementAsFunction(__VLS_intrinsicElements.form, __VLS_intrinsicElements.form)({
                ...{ onSubmit: (__VLS_ctx.createDomain) },
                ...{ class: ("domain-form") },
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.input, __VLS_intrinsicElements.input)({
                placeholder: ("portal.escola.com.br"),
                required: (true),
            });
            (__VLS_ctx.domainForm.hostname);
            __VLS_elementAsFunction(__VLS_intrinsicElements.select, __VLS_intrinsicElements.select)({
                value: ((__VLS_ctx.domainForm.surface)),
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
                value: ("admin"),
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
                value: ("public"),
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
                value: ("family"),
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
                value: ("student"),
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
                value: ("teacher"),
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                ...{ class: ("primary") },
            });
            for (const [d] of __VLS_getVForSourceType((__VLS_ctx.domains))) {
                __VLS_elementAsFunction(__VLS_intrinsicElements.article, __VLS_intrinsicElements.article)({
                    ...{ class: ("domain-card") },
                    key: ((d.id)),
                });
                __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                    ...{ class: ("domain-head") },
                });
                __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({});
                __VLS_elementAsFunction(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
                (d.hostname);
                __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
                (d.surface);
                (d.is_canonical ? 'canônico' : 'personalizado');
                __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({
                    ...{ class: ("status-pill") },
                });
                (d.status);
                __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                    ...{ class: ("domain-meta") },
                });
                __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
                (d.certificate_status || '—');
                __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
                (d.verification_status || '—');
                if (d.provider) {
                    __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
                    (d.provider);
                }
                if (d.routing_record) {
                    __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                        ...{ class: ("dns-box") },
                    });
                    __VLS_elementAsFunction(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
                    __VLS_elementAsFunction(__VLS_intrinsicElements.code, __VLS_intrinsicElements.code)({});
                    (d.routing_record.type);
                    (d.routing_record.name);
                    __VLS_elementAsFunction(__VLS_intrinsicElements.code, __VLS_intrinsicElements.code)({});
                    (d.routing_record.value);
                    __VLS_elementAsFunction(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
                    (d.routing_record.apex_note);
                    __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({});
                    __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                        ...{ onClick: (...[$event]) => {
                                if (!(!((!__VLS_ctx.ready))))
                                    return;
                                if (!(!((!__VLS_ctx.auth))))
                                    return;
                                if (!(!((!__VLS_ctx.selected))))
                                    return;
                                if (!((d.routing_record)))
                                    return;
                                __VLS_ctx.copy(d.routing_record.name);
                            } },
                        ...{ class: ("ghost-dark") },
                    });
                    __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                        ...{ onClick: (...[$event]) => {
                                if (!(!((!__VLS_ctx.ready))))
                                    return;
                                if (!(!((!__VLS_ctx.auth))))
                                    return;
                                if (!(!((!__VLS_ctx.selected))))
                                    return;
                                if (!((d.routing_record)))
                                    return;
                                __VLS_ctx.copy(d.routing_record.value);
                            } },
                        ...{ class: ("ghost-dark") },
                    });
                }
                if (d.verification_record && d.verification_status !== 'verified') {
                    __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                        ...{ class: ("dns-box") },
                    });
                    __VLS_elementAsFunction(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
                    __VLS_elementAsFunction(__VLS_intrinsicElements.code, __VLS_intrinsicElements.code)({});
                    (d.verification_record.name);
                    __VLS_elementAsFunction(__VLS_intrinsicElements.code, __VLS_intrinsicElements.code)({});
                    (d.verification_record.value);
                    __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({});
                    __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                        ...{ onClick: (...[$event]) => {
                                if (!(!((!__VLS_ctx.ready))))
                                    return;
                                if (!(!((!__VLS_ctx.auth))))
                                    return;
                                if (!(!((!__VLS_ctx.selected))))
                                    return;
                                if (!((d.verification_record && d.verification_status !== 'verified')))
                                    return;
                                __VLS_ctx.copy(d.verification_record.name);
                            } },
                        ...{ class: ("ghost-dark") },
                    });
                    __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                        ...{ onClick: (...[$event]) => {
                                if (!(!((!__VLS_ctx.ready))))
                                    return;
                                if (!(!((!__VLS_ctx.auth))))
                                    return;
                                if (!(!((!__VLS_ctx.selected))))
                                    return;
                                if (!((d.verification_record && d.verification_status !== 'verified')))
                                    return;
                                __VLS_ctx.copy(d.verification_record.value);
                            } },
                        ...{ class: ("ghost-dark") },
                    });
                }
                if (d.provider_validation_records?.length) {
                    __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                        ...{ class: ("dns-box") },
                    });
                    __VLS_elementAsFunction(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
                    for (const [record] of __VLS_getVForSourceType((d.provider_validation_records))) {
                        __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                            key: ((`${record.purpose}-${record.type}-${record.name}`)),
                        });
                        __VLS_elementAsFunction(__VLS_intrinsicElements.code, __VLS_intrinsicElements.code)({});
                        (record.purpose);
                        (record.type);
                        (record.name);
                        __VLS_elementAsFunction(__VLS_intrinsicElements.code, __VLS_intrinsicElements.code)({});
                        (record.value);
                        if (record.status) {
                            __VLS_elementAsFunction(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
                            (record.status);
                        }
                        __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({});
                        __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                            ...{ onClick: (...[$event]) => {
                                    if (!(!((!__VLS_ctx.ready))))
                                        return;
                                    if (!(!((!__VLS_ctx.auth))))
                                        return;
                                    if (!(!((!__VLS_ctx.selected))))
                                        return;
                                    if (!((d.provider_validation_records?.length)))
                                        return;
                                    __VLS_ctx.copy(String(record.name));
                                } },
                            ...{ class: ("ghost-dark") },
                        });
                        __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                            ...{ onClick: (...[$event]) => {
                                    if (!(!((!__VLS_ctx.ready))))
                                        return;
                                    if (!(!((!__VLS_ctx.auth))))
                                        return;
                                    if (!(!((!__VLS_ctx.selected))))
                                        return;
                                    if (!((d.provider_validation_records?.length)))
                                        return;
                                    __VLS_ctx.copy(String(record.value));
                                } },
                            ...{ class: ("ghost-dark") },
                        });
                    }
                }
                if (!d.is_canonical) {
                    __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                        ...{ class: ("row-actions") },
                    });
                    if (d.verification_status !== 'verified') {
                        __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                            ...{ onClick: (...[$event]) => {
                                    if (!(!((!__VLS_ctx.ready))))
                                        return;
                                    if (!(!((!__VLS_ctx.auth))))
                                        return;
                                    if (!(!((!__VLS_ctx.selected))))
                                        return;
                                    if (!((!d.is_canonical)))
                                        return;
                                    if (!((d.verification_status !== 'verified')))
                                        return;
                                    __VLS_ctx.verifyDomain(d);
                                } },
                            ...{ class: ("ghost-dark") },
                        });
                    }
                    if (d.verification_status === 'verified' && d.status !== 'active') {
                        __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                            ...{ onClick: (...[$event]) => {
                                    if (!(!((!__VLS_ctx.ready))))
                                        return;
                                    if (!(!((!__VLS_ctx.auth))))
                                        return;
                                    if (!(!((!__VLS_ctx.selected))))
                                        return;
                                    if (!((!d.is_canonical)))
                                        return;
                                    if (!((d.verification_status === 'verified' && d.status !== 'active')))
                                        return;
                                    __VLS_ctx.refreshDomain(d);
                                } },
                            ...{ class: ("ghost-dark") },
                        });
                    }
                    __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                        ...{ onClick: (...[$event]) => {
                                if (!(!((!__VLS_ctx.ready))))
                                    return;
                                if (!(!((!__VLS_ctx.auth))))
                                    return;
                                if (!(!((!__VLS_ctx.selected))))
                                    return;
                                if (!((!d.is_canonical)))
                                    return;
                                __VLS_ctx.disableDomain(d);
                            } },
                        ...{ class: ("danger-outline") },
                    });
                }
                if (d.last_error) {
                    __VLS_elementAsFunction(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({
                        ...{ class: ("inline-error") },
                    });
                    (d.last_error);
                }
            }
            __VLS_elementAsFunction(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
                ...{ class: ("panel app-factory") },
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: ("section-title") },
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
            (__VLS_ctx.apps.builds?.length || 0);
            __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: ("build-selection") },
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.fieldset, __VLS_intrinsicElements.fieldset)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.legend, __VLS_intrinsicElements.legend)({});
            for (const [option] of __VLS_getVForSourceType((__VLS_ctx.productOptions))) {
                __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({
                    key: ((option[0])),
                });
                __VLS_elementAsFunction(__VLS_intrinsicElements.input, __VLS_intrinsicElements.input)({
                    type: ("checkbox"),
                    value: ((option[0])),
                });
                (__VLS_ctx.selectedProducts);
                (option[1]);
            }
            __VLS_elementAsFunction(__VLS_intrinsicElements.fieldset, __VLS_intrinsicElements.fieldset)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.legend, __VLS_intrinsicElements.legend)({});
            for (const [option] of __VLS_getVForSourceType((__VLS_ctx.platformOptions))) {
                __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({
                    key: ((option[0])),
                });
                __VLS_elementAsFunction(__VLS_intrinsicElements.input, __VLS_intrinsicElements.input)({
                    type: ("checkbox"),
                    value: ((option[0])),
                });
                (__VLS_ctx.selectedPlatforms);
                (option[1]);
            }
            __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: ("entitlements") },
            });
            for (const [item] of __VLS_getVForSourceType((__VLS_ctx.apps.entitlements))) {
                __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({
                    key: ((item.id)),
                    ...{ class: ("status-pill") },
                });
                (item.app_product);
                (item.state);
            }
            __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: ("app-actions") },
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                ...{ onClick: (__VLS_ctx.activateEntitlements) },
                ...{ class: ("ghost-dark") },
                disabled: ((__VLS_ctx.busy)),
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                ...{ onClick: (__VLS_ctx.manifestAndBuild) },
                ...{ class: ("primary") },
                disabled: ((__VLS_ctx.busy)),
            });
            for (const [build] of __VLS_getVForSourceType((__VLS_ctx.apps.builds))) {
                __VLS_elementAsFunction(__VLS_intrinsicElements.article, __VLS_intrinsicElements.article)({
                    ...{ class: ("build-card") },
                    key: ((build.build_id)),
                });
                __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                    ...{ class: ("section-title") },
                });
                __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({});
                __VLS_elementAsFunction(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
                (build.build_id);
                __VLS_elementAsFunction(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
                (build.created_at);
                (build.requested_platforms?.join(', '));
                __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({
                    ...{ class: ("status-pill") },
                });
                (build.status);
                __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                    ...{ class: ("job-grid") },
                });
                for (const [job] of __VLS_getVForSourceType((build.jobs))) {
                    __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                        key: ((job.id)),
                    });
                    __VLS_elementAsFunction(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
                    (job.app_product);
                    (job.platform);
                    __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
                    (job.status);
                    (job.required_os);
                    (job.architecture);
                    if (job.last_error) {
                        __VLS_elementAsFunction(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({
                            ...{ class: ("inline-error") },
                        });
                        (job.last_error);
                    }
                }
                if (build.artifacts?.length) {
                    __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                        ...{ class: ("artifact-list") },
                    });
                    for (const [artifact] of __VLS_getVForSourceType((build.artifacts))) {
                        __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                            key: ((artifact.id)),
                        });
                        __VLS_elementAsFunction(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
                        (artifact.filename);
                        __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
                        (artifact.artifact_kind);
                        (artifact.platform);
                        (artifact.architecture);
                        (artifact.signed_state);
                        __VLS_elementAsFunction(__VLS_intrinsicElements.code, __VLS_intrinsicElements.code)({});
                        (artifact.sha256);
                    }
                }
                if (build.status === 'failed') {
                    __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                        ...{ onClick: (...[$event]) => {
                                if (!(!((!__VLS_ctx.ready))))
                                    return;
                                if (!(!((!__VLS_ctx.auth))))
                                    return;
                                if (!(!((!__VLS_ctx.selected))))
                                    return;
                                if (!((build.status === 'failed')))
                                    return;
                                __VLS_ctx.retryBuild(build);
                            } },
                        ...{ class: ("ghost-dark") },
                    });
                }
            }
            if (!__VLS_ctx.apps.builds?.length) {
                __VLS_elementAsFunction(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({
                    ...{ class: ("empty") },
                });
            }
            __VLS_elementAsFunction(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
                ...{ class: ("panel") },
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
            for (const [r] of __VLS_getVForSourceType((__VLS_ctx.apps.releases))) {
                __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                    ...{ class: ("list-row") },
                    key: ((r.id)),
                });
                __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({});
                __VLS_elementAsFunction(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
                (r.version);
                (r.channel);
                __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
                (r.state);
                __VLS_elementAsFunction(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
                (r.created_at);
            }
            if (!__VLS_ctx.apps.releases?.length) {
                __VLS_elementAsFunction(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({
                    ...{ class: ("empty") },
                });
            }
        }
        __VLS_elementAsFunction(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
            ...{ class: ("panel logs-panel") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: ("section-title") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
        (__VLS_ctx.selected ? `Filtrando por ${__VLS_ctx.selected.trade_name}` : 'Toda a plataforma');
        __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
        (__VLS_ctx.logs.length);
        __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: ("log-filters") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.input, __VLS_intrinsicElements.input)({
            placeholder: ("Correlation ID"),
        });
        (__VLS_ctx.logFilters.correlation_id);
        __VLS_elementAsFunction(__VLS_intrinsicElements.input, __VLS_intrinsicElements.input)({
            placeholder: ("Serviço, ex.: pige360-api"),
        });
        (__VLS_ctx.logFilters.service);
        __VLS_elementAsFunction(__VLS_intrinsicElements.select, __VLS_intrinsicElements.select)({
            value: ((__VLS_ctx.logFilters.plane)),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
            value: (""),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
            value: ("platform"),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
            value: ("tenant"),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.select, __VLS_intrinsicElements.select)({
            value: ((__VLS_ctx.logFilters.level)),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
            value: (""),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
            value: ("info"),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
            value: ("warning"),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
            value: ("error"),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.input, __VLS_intrinsicElements.input)({
            type: ("number"),
            min: ("1"),
            max: ("10080"),
            title: ("Janela em minutos"),
        });
        (__VLS_ctx.logFilters.minutes);
        __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
            ...{ onClick: (__VLS_ctx.loadLogs) },
            ...{ class: ("primary") },
        });
        if (__VLS_ctx.lastLogQuery) {
            __VLS_elementAsFunction(__VLS_intrinsicElements.code, __VLS_intrinsicElements.code)({
                ...{ class: ("query-code") },
            });
            (__VLS_ctx.lastLogQuery);
        }
        for (const [l] of __VLS_getVForSourceType((__VLS_ctx.logs))) {
            __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: ("log-row") },
                key: ((l.timestamp_ns + JSON.stringify(l.labels))),
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: ("log-tags") },
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
            (l.labels?.service || 'serviço');
            if (l.labels?.tenant_code) {
                __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
                (l.labels.tenant_code);
            }
            if (l.event?.correlation_id) {
                __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
                (l.event.correlation_id);
            }
            __VLS_elementAsFunction(__VLS_intrinsicElements.pre, __VLS_intrinsicElements.pre)({});
            (l.event ? JSON.stringify(l.event, null, 2) : l.message);
        }
        if (!__VLS_ctx.logs.length) {
            __VLS_elementAsFunction(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({
                ...{ class: ("empty") },
            });
        }
    }
    ['center', 'login-page', 'platform-login', 'login-card', 'mark', 'eyebrow', 'flash', 'error', 'primary', 'console', 'brand', 'mark', 'active', 'active', 'logout', 'flash', 'error', 'flash', 'success', 'eyebrow', 'ghost-dark', 'metrics', 'grid', 'two', 'panel', 'form', 'helper', 'primary', 'panel', 'list-row', 'grid', 'two', 'panel', 'section-title', 'status-pill', 'facts', 'panel', 'section-title', 'list-row', 'panel', 'section-title', 'list-row', 'grid', 'two', 'panel', 'form', 'facts', 'row-actions', 'danger-outline', 'primary', 'panel', 'form', 'primary', 'support-session', 'danger-outline', 'panel', 'form', 'section-title', 'quota-grid', 'entitlements', 'status-pill', 'primary', 'panel', 'section-title', 'domain-form', 'primary', 'domain-card', 'domain-head', 'status-pill', 'domain-meta', 'dns-box', 'ghost-dark', 'ghost-dark', 'dns-box', 'ghost-dark', 'ghost-dark', 'dns-box', 'ghost-dark', 'ghost-dark', 'row-actions', 'ghost-dark', 'ghost-dark', 'danger-outline', 'inline-error', 'panel', 'app-factory', 'section-title', 'build-selection', 'entitlements', 'status-pill', 'app-actions', 'ghost-dark', 'primary', 'build-card', 'section-title', 'status-pill', 'job-grid', 'inline-error', 'artifact-list', 'ghost-dark', 'empty', 'panel', 'list-row', 'empty', 'panel', 'logs-panel', 'section-title', 'log-filters', 'primary', 'query-code', 'log-row', 'log-tags', 'empty',];
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
            CommercialAdministrationPanel: CommercialAdministrationPanel,
            OperationalAdministrationPanel: OperationalAdministrationPanel,
            api: api,
            ready: ready,
            auth: auth,
            busy: busy,
            error: error,
            notice: notice,
            email: email,
            password: password,
            tenants: tenants,
            status: status,
            audit: audit,
            support: support,
            inventory: inventory,
            platformUsers: platformUsers,
            selected: selected,
            apps: apps,
            branding: branding,
            domains: domains,
            quotas: quotas,
            logs: logs,
            lastLogQuery: lastLogQuery,
            form: form,
            supportForm: supportForm,
            supportEndReason: supportEndReason,
            lifecycleReason: lifecycleReason,
            quotaReason: quotaReason,
            domainForm: domainForm,
            logFilters: logFilters,
            quotaForm: quotaForm,
            selectedProducts: selectedProducts,
            selectedPlatforms: selectedPlatforms,
            productOptions: productOptions,
            platformOptions: platformOptions,
            handlePanelFeedback: handlePanelFeedback,
            canonicalDomainHost: canonicalDomainHost,
            selectedSupportSessions: selectedSupportSessions,
            canManagePlatformUsers: canManagePlatformUsers,
            load: load,
            login: login,
            logout: logout,
            createTenant: createTenant,
            choose: choose,
            createSupport: createSupport,
            revokeSupport: revokeSupport,
            changeTenantState: changeTenantState,
            updateQuotas: updateQuotas,
            setPlatformUserState: setPlatformUserState,
            activateEntitlements: activateEntitlements,
            manifestAndBuild: manifestAndBuild,
            retryBuild: retryBuild,
            createDomain: createDomain,
            verifyDomain: verifyDomain,
            refreshDomain: refreshDomain,
            disableDomain: disableDomain,
            copy: copy,
            loadLogs: loadLogs,
        };
    },
});
export default (await import('vue')).defineComponent({
    setup() {
        return {};
    },
});
; /* PartiallyEnd: #4569/main.vue */
