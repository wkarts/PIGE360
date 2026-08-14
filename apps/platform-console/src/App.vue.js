import { onMounted, reactive, ref } from "vue";
import { Pige360SessionClient } from "@pige360/auth";
const api = new Pige360SessionClient();
const ready = ref(false), auth = ref(false), busy = ref(false), error = ref(""), notice = ref(""), email = ref(""), password = ref("");
const tenants = ref([]), status = ref({}), audit = ref([]), support = ref([]), selected = ref(null), apps = ref({ entitlements: [], manifests: [], builds: [], releases: [] }), branding = ref({});
const form = reactive({ code: "", legal_name: "", trade_name: "", hostname: "", owner_email: "", owner_password: "" });
const supportForm = reactive({ reason: "", ticket: "", minutes: 30 });
const appProduct = ref("family-mobile");
const platform = ref("pwa");
function msg(e) { const p = e?.problem; return p?.detail || (e instanceof Error ? e.message : "Erro inesperado"); }
async function load() { const [t, s, a, ss] = await Promise.all([api.request("/platform/tenants"), api.request("/platform/status"), api.request("/platform/audit?limit=50"), api.request("/platform/support-sessions?active_only=true")]); tenants.value = t.items || []; status.value = s; audit.value = a.items || []; support.value = ss.items || []; if (selected.value) {
    const fresh = tenants.value.find(x => x.id === selected.value?.id);
    if (fresh)
        selected.value = fresh;
    await loadTenant();
} }
async function loadTenant() { if (!selected.value)
    return; [apps.value, branding.value] = await Promise.all([api.request(`/platform/tenants/${selected.value.id}/apps`), api.request(`/platform/tenants/${selected.value.id}/branding`)]); }
async function boot() { try {
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
} }
async function login() { try {
    await api.login(email.value, password.value);
    if (api.claims()?.plane !== 'platform')
        throw new Error('Use uma conta do Control Plane.');
    auth.value = true;
    await load();
}
catch (e) {
    error.value = msg(e);
} }
async function logout() { await api.logout(); auth.value = false; }
async function createTenant() { busy.value = true; try {
    await api.request('/platform/tenants', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(form) });
    notice.value = 'Tenant provisionado.';
    Object.assign(form, { code: "", legal_name: "", trade_name: "", hostname: "", owner_email: "", owner_password: "" });
    await load();
}
catch (e) {
    error.value = msg(e);
}
finally {
    busy.value = false;
} }
async function choose(t) { selected.value = t; await loadTenant(); }
async function createSupport() { if (!selected.value)
    return; try {
    await api.request(`/platform/tenants/${selected.value.id}/support-sessions`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(supportForm) });
    notice.value = 'Sessão de suporte auditada criada.';
    await load();
}
catch (e) {
    error.value = msg(e);
} }
async function entitlement() { if (!selected.value)
    return; try {
    await api.request(`/platform/tenants/${selected.value.id}/apps/entitlements`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ app_product: appProduct.value, state: 'active', contract_reference: 'console' }) });
    notice.value = 'Entitlement atualizado.';
    await loadTenant();
}
catch (e) {
    error.value = msg(e);
} }
async function manifestAndBuild() { if (!selected.value)
    return; const brandVersion = branding.value.active_version; if (!brandVersion) {
    error.value = 'Publique o branding do tenant antes de gerar aplicativos.';
    return;
} const domain = selected.value.domains?.find((d) => d.is_canonical)?.hostname || selected.value.domains?.[0]?.hostname; if (!domain) {
    error.value = 'Tenant sem domínio provisionado.';
    return;
} const slug = selected.value.code.replace(/[^a-z0-9]/g, ''); const product = appProduct.value; const idProduct = product.replace(/-mobile$/, '').replace(/-/g, '.'); try {
    const mf = await api.request(`/platform/tenants/${selected.value.id}/apps/manifests`, { method: 'POST', headers: { 'Content-Type': 'application/json', 'Idempotency-Key': `manifest-${crypto.randomUUID()}` }, body: JSON.stringify({ tenant_code: selected.value.code, brand_version: brandVersion, release_channel: 'stable', apps: { [product]: { enabled: true, display_name: `${selected.value.trade_name} ${product}`, identifier: `br.com.${slug}.${idProduct}`, api_url: `https://${domain}`, web_url: `https://${domain}`, update_url: `https://${domain}/apps`, features: { finance: true, attendance: true }, signing: {} } }, metadata: { created_from: 'platform-console' } }) });
    const build = await api.request(`/platform/tenants/${selected.value.id}/apps/builds`, { method: 'POST', headers: { 'Content-Type': 'application/json', 'Idempotency-Key': `build-${crypto.randomUUID()}` }, body: JSON.stringify({ manifest_id: mf.id, platforms: [platform.value], products: [product] }) });
    notice.value = `Build ${build.id} enfileirado.`;
    await loadTenant();
}
catch (e) {
    error.value = msg(e);
} }
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
            __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.input, __VLS_intrinsicElements.input)({
                pattern: ("[a-z0-9-]+"),
                required: (true),
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
                placeholder: ("admin.escola.com.br"),
                required: (true),
            });
            (__VLS_ctx.form.hostname);
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
        }
        else {
            __VLS_elementAsFunction(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
                ...{ class: ("grid two") },
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: ("panel") },
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
            (__VLS_ctx.branding.active_version || 0);
            (__VLS_ctx.branding.state);
            for (const [d] of __VLS_getVForSourceType((__VLS_ctx.selected.domains))) {
                __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                    key: ((d.id)),
                });
                __VLS_elementAsFunction(__VLS_intrinsicElements.dt, __VLS_intrinsicElements.dt)({});
                __VLS_elementAsFunction(__VLS_intrinsicElements.dd, __VLS_intrinsicElements.dd)({});
                (d.hostname);
                (d.status);
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
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
                ...{ class: ("panel") },
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: ("section-title") },
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
            (__VLS_ctx.apps.builds?.length || 0);
            __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: ("app-actions") },
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.select, __VLS_intrinsicElements.select)({
                value: ((__VLS_ctx.appProduct)),
            });
            for (const [p] of __VLS_getVForSourceType((['family-mobile', 'teacher-mobile', 'student-mobile', 'admin-mobile', 'pos-mobile', 'kiosk', 'timeclock', 'desktop-admin', 'pos-desktop', 'pwa']))) {
                __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
                    key: ((p)),
                });
                (p);
            }
            __VLS_elementAsFunction(__VLS_intrinsicElements.select, __VLS_intrinsicElements.select)({
                value: ((__VLS_ctx.platform)),
            });
            for (const [p] of __VLS_getVForSourceType((['pwa', 'android-apk', 'android-aab', 'ios-app', 'ios-xcarchive', 'ios-ipa-unsigned', 'windows-x64', 'windows-x86', 'linux-x64', 'linux-arm64', 'macos-intel', 'macos-apple']))) {
                __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
                    key: ((p)),
                });
                (p);
            }
            __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                ...{ onClick: (__VLS_ctx.entitlement) },
                ...{ class: ("ghost-dark") },
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                ...{ onClick: (__VLS_ctx.manifestAndBuild) },
                ...{ class: ("primary") },
            });
            for (const [b] of __VLS_getVForSourceType((__VLS_ctx.apps.builds))) {
                __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                    ...{ class: ("list-row") },
                    key: ((b.id)),
                });
                __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({});
                __VLS_elementAsFunction(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
                (b.id);
                __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
                (b.status || b.state);
                (b.created_at);
                __VLS_elementAsFunction(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
                (b.jobs?.length || 0);
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
    }
    ['center', 'login-page', 'platform-login', 'login-card', 'mark', 'eyebrow', 'flash', 'error', 'primary', 'console', 'brand', 'mark', 'active', 'logout', 'flash', 'error', 'flash', 'success', 'eyebrow', 'ghost-dark', 'metrics', 'grid', 'two', 'panel', 'form', 'primary', 'panel', 'list-row', 'grid', 'two', 'panel', 'facts', 'panel', 'form', 'primary', 'panel', 'section-title', 'app-actions', 'ghost-dark', 'primary', 'list-row', 'panel', 'list-row', 'empty',];
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
            selected: selected,
            apps: apps,
            branding: branding,
            form: form,
            supportForm: supportForm,
            appProduct: appProduct,
            platform: platform,
            load: load,
            login: login,
            logout: logout,
            createTenant: createTenant,
            choose: choose,
            createSupport: createSupport,
            entitlement: entitlement,
            manifestAndBuild: manifestAndBuild,
        };
    },
});
export default (await import('vue')).defineComponent({
    setup() {
        return {};
    },
});
; /* PartiallyEnd: #4569/main.vue */
