import { computed, onMounted, reactive, ref } from "vue";
import { Pige360SessionClient } from "@pige360/auth";
const api = new Pige360SessionClient();
const ready = ref(false), auth = ref(false), busy = ref(false), error = ref(""), notice = ref(""), email = ref(""), password = ref("");
const tenants = ref([]), selectedTenant = ref("");
const kit = ref({ payload: {}, assets: [], versions: [] });
const preview = ref(null);
const form = reactive({ legal_name: "", trade_name: "", short_name: "", app_display_name: "", primary_domain: "", primary_color: "#006D77", secondary_color: "#0D1B2A", accent_color: "#F59E0B", typography_family: "Inter", co_branding_policy: "disabled" });
const plane = computed(() => api.claims()?.plane || "tenant");
const target = computed(() => plane.value === 'platform' && selectedTenant.value ? `/platform/tenants/${selectedTenant.value}/branding` : "/branding");
function msg(e) { const p = e?.problem; return p?.detail || (e instanceof Error ? e.message : "Erro inesperado"); }
function fill() { Object.assign(form, { legal_name: "", trade_name: "", short_name: "", app_display_name: "", primary_domain: "", primary_color: "#006D77", secondary_color: "#0D1B2A", accent_color: "#F59E0B", typography_family: "Inter", co_branding_policy: "disabled" }, kit.value.payload || {}); document.documentElement.style.setProperty('--brand-primary', form.primary_color); document.documentElement.style.setProperty('--brand-secondary', form.secondary_color); }
async function load() { if (plane.value === 'platform') {
    tenants.value = (await api.request("/platform/tenants")).items || [];
    if (!selectedTenant.value)
        selectedTenant.value = tenants.value[0]?.id || "";
    if (!selectedTenant.value)
        return;
} kit.value = await api.request(target.value); fill(); }
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
    auth.value = true;
    await load();
}
catch (e) {
    error.value = msg(e);
} }
async function logout() { await api.logout(); auth.value = false; }
async function changeTenant() { preview.value = null; await load(); }
async function runPreview() { try {
    preview.value = await api.request(`${target.value}/preview`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ changes: { ...form } }) });
}
catch (e) {
    error.value = msg(e);
} }
async function publish() { busy.value = true; try {
    const result = await api.request(`${target.value}/publish`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ payload: { ...form }, reason: "Publicação aprovada no Branding Studio" }) });
    notice.value = `Branding v${result.version} publicado.`;
    await load();
}
catch (e) {
    error.value = msg(e);
}
finally {
    busy.value = false;
} }
async function rollback(version) { if (!confirm(`Restaurar a versão ${version}?`))
    return; try {
    await api.request(`${target.value}/rollback`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ version, reason: "Rollback solicitado no Branding Studio" }) });
    notice.value = `Versão ${version} restaurada.`;
    await load();
}
catch (e) {
    error.value = msg(e);
} }
async function upload(event, category) { const file = event.target.files?.[0]; if (!file)
    return; busy.value = true; try {
    const b64 = await new Promise((resolve, reject) => { const r = new FileReader(); r.onerror = () => reject(r.error); r.onload = () => resolve(String(r.result).split(',')[1] || ''); r.readAsDataURL(file); });
    await api.request(`${target.value}/assets`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ category, filename: file.name, mime_type: file.type || 'application/octet-stream', content_base64: b64 }) });
    notice.value = "Ativo enviado e verificado por SHA-256.";
    await load();
}
catch (e) {
    error.value = msg(e);
}
finally {
    busy.value = false;
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
            ...{ class: ("login-page") },
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
            ...{ class: ("mobile-shell") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.header, __VLS_intrinsicElements.header)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: ("brand") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: ("mark") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
        (__VLS_ctx.plane === 'platform' ? 'PIGE360' : __VLS_ctx.form.short_name || __VLS_ctx.form.trade_name || 'Branding');
        __VLS_elementAsFunction(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
            ...{ onClick: (__VLS_ctx.logout) },
            ...{ class: ("ghost") },
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
        if (__VLS_ctx.plane === 'platform') {
            __VLS_elementAsFunction(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
                ...{ class: ("panel") },
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.select, __VLS_intrinsicElements.select)({
                ...{ onChange: (__VLS_ctx.changeTenant) },
                value: ((__VLS_ctx.selectedTenant)),
            });
            for (const [t] of __VLS_getVForSourceType((__VLS_ctx.tenants))) {
                __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
                    key: ((t.id)),
                    value: ((t.id)),
                });
                (t.trade_name);
                (t.code);
            }
        }
        __VLS_elementAsFunction(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
            ...{ class: ("studio-grid") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.form, __VLS_intrinsicElements.form)({
            ...{ onSubmit: (__VLS_ctx.runPreview) },
            ...{ class: ("panel form") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: ("section-title") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
        (__VLS_ctx.kit.state);
        (__VLS_ctx.kit.active_version || 0);
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
            required: (true),
        });
        (__VLS_ctx.form.short_name);
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.input, __VLS_intrinsicElements.input)({
            required: (true),
        });
        (__VLS_ctx.form.app_display_name);
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.input, __VLS_intrinsicElements.input)({
            placeholder: ("www.escola.com.br"),
            required: (true),
        });
        (__VLS_ctx.form.primary_domain);
        __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: ("colors") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.input, __VLS_intrinsicElements.input)({
            type: ("color"),
        });
        (__VLS_ctx.form.primary_color);
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.input, __VLS_intrinsicElements.input)({
            type: ("color"),
        });
        (__VLS_ctx.form.secondary_color);
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.input, __VLS_intrinsicElements.input)({
            type: ("color"),
        });
        (__VLS_ctx.form.accent_color);
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.input, __VLS_intrinsicElements.input)({});
        (__VLS_ctx.form.typography_family);
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.select, __VLS_intrinsicElements.select)({
            value: ((__VLS_ctx.form.co_branding_policy)),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
            value: ("disabled"),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
            value: ("optional"),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
            value: ("required"),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: ("actions") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
            ...{ class: ("ghost-dark") },
            type: ("submit"),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
            ...{ onClick: (__VLS_ctx.publish) },
            ...{ class: ("primary") },
            type: ("button"),
            disabled: ((__VLS_ctx.busy)),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: ("panel preview") },
            ...{ style: (({ '--preview-primary': __VLS_ctx.form.primary_color, '--preview-secondary': __VLS_ctx.form.secondary_color, '--preview-accent': __VLS_ctx.form.accent_color })) },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({
            ...{ class: ("eyebrow") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: ("preview-header") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: ("preview-logo") },
        });
        ((__VLS_ctx.form.short_name || 'E').slice(0, 2).toUpperCase());
        __VLS_elementAsFunction(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
        (__VLS_ctx.form.trade_name || 'Nome da instituição');
        __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: ("preview-hero") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
        (__VLS_ctx.form.app_display_name || __VLS_ctx.form.trade_name);
        __VLS_elementAsFunction(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({});
        if (__VLS_ctx.preview?.contrast) {
            __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: ("contrast") },
            });
            for (const [c, key] of __VLS_getVForSourceType((__VLS_ctx.preview.contrast))) {
                __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                    key: ((key)),
                });
                __VLS_elementAsFunction(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
                (key);
                __VLS_elementAsFunction(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
                (c.on_white.ratio);
                (c.on_white.passes_aa ? 'AA' : 'falha AA');
                __VLS_elementAsFunction(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
                (c.on_dark.ratio);
                (c.on_dark.passes_aa ? 'AA' : 'falha AA');
            }
        }
        __VLS_elementAsFunction(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
            ...{ class: ("grid two") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: ("panel") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({
            ...{ class: ("upload") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.input, __VLS_intrinsicElements.input)({
            ...{ onChange: (...[$event]) => {
                    if (!(!((!__VLS_ctx.ready))))
                        return;
                    if (!(!((!__VLS_ctx.auth))))
                        return;
                    __VLS_ctx.upload($event, 'logo_primary_light');
                } },
            type: ("file"),
            accept: ("image/png,image/jpeg,image/webp,image/svg+xml"),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({
            ...{ class: ("upload") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.input, __VLS_intrinsicElements.input)({
            ...{ onChange: (...[$event]) => {
                    if (!(!((!__VLS_ctx.ready))))
                        return;
                    if (!(!((!__VLS_ctx.auth))))
                        return;
                    __VLS_ctx.upload($event, 'app_icon_source');
                } },
            type: ("file"),
            accept: ("image/png,image/jpeg,image/webp,image/svg+xml"),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({
            ...{ class: ("upload") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.input, __VLS_intrinsicElements.input)({
            ...{ onChange: (...[$event]) => {
                    if (!(!((!__VLS_ctx.ready))))
                        return;
                    if (!(!((!__VLS_ctx.auth))))
                        return;
                    __VLS_ctx.upload($event, 'splash_source');
                } },
            type: ("file"),
            accept: ("image/png,image/jpeg,image/webp,image/svg+xml"),
        });
        for (const [a] of __VLS_getVForSourceType((__VLS_ctx.kit.assets))) {
            __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: ("list-row") },
                key: ((a.id)),
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
            (a.category);
            __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
            (a.original_filename);
            __VLS_elementAsFunction(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
            (a.sha256?.slice(0, 12));
        }
        __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: ("panel") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
        for (const [v] of __VLS_getVForSourceType((__VLS_ctx.kit.versions))) {
            __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: ("list-row") },
                key: ((v.id)),
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
            (v.version);
            (v.state);
            __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
            (v.sha256?.slice(0, 16));
            if (v.version !== __VLS_ctx.kit.active_version) {
                __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                    ...{ onClick: (...[$event]) => {
                            if (!(!((!__VLS_ctx.ready))))
                                return;
                            if (!(!((!__VLS_ctx.auth))))
                                return;
                            if (!((v.version !== __VLS_ctx.kit.active_version)))
                                return;
                            __VLS_ctx.rollback(v.version);
                        } },
                    ...{ class: ("small") },
                });
            }
        }
    }
    ['center', 'login-page', 'login-card', 'mark', 'eyebrow', 'flash', 'error', 'primary', 'mobile-shell', 'brand', 'mark', 'ghost', 'flash', 'error', 'flash', 'success', 'panel', 'studio-grid', 'panel', 'form', 'section-title', 'colors', 'actions', 'ghost-dark', 'primary', 'panel', 'preview', 'eyebrow', 'preview-header', 'preview-logo', 'preview-hero', 'contrast', 'grid', 'two', 'panel', 'upload', 'upload', 'upload', 'list-row', 'panel', 'list-row', 'small',];
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
            selectedTenant: selectedTenant,
            kit: kit,
            preview: preview,
            form: form,
            plane: plane,
            login: login,
            logout: logout,
            changeTenant: changeTenant,
            runPreview: runPreview,
            publish: publish,
            rollback: rollback,
            upload: upload,
        };
    },
});
export default (await import('vue')).defineComponent({
    setup() {
        return {};
    },
});
; /* PartiallyEnd: #4569/main.vue */
