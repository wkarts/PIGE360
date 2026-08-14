import { onMounted, reactive, ref } from "vue";
const props = defineProps();
const emit = defineEmits();
const loading = ref(false), notice = ref("");
const locations = ref([]), menus = ref([]), wallets = ref([]), subsidies = ref([]), students = ref([]), products = ref([]);
const locationForm = reactive({ unit_id: "", code: "CANT-01", name: "Cantina Principal" });
const menuForm = reactive({ canteen_location_id: "", name: "Cardápio Regular", starts_on: "", ends_on: "" });
const walletForm = reactive({ student_id: "", daily_limit: "50.00", weekly_limit: "250.00" });
const creditForm = reactive({ wallet_id: "", amount: "", method: "pix", external_reference: "", reason: "Recarga da carteira" });
const subsidyForm = reactive({ student_id: "", subsidy_type: "fixed", amount: "", percentage: "", valid_from: new Date().toISOString().slice(0, 10), valid_until: "", reason: "Benefício institucional" });
function msg(e) { return e instanceof Error ? e.message : "Erro inesperado"; }
async function request(p, i = {}) { return props.api.request(p, i); }
async function post(p, b, key) { const h = { "Content-Type": "application/json" }; if (key)
    h["Idempotency-Key"] = key; return request(p, { method: "POST", headers: h, body: JSON.stringify(b) }); }
async function load() { loading.value = true; try {
    const [l, m, w, s, refs, p] = await Promise.all([request("/canteen/locations"), request("/canteen/menus"), request("/canteen/wallets"), request("/canteen/subsidies"), request("/references/catalog"), request("/products")]);
    locations.value = l.items || [];
    menus.value = m.items || [];
    wallets.value = w.items || [];
    subsidies.value = s.items || [];
    students.value = refs.students || [];
    products.value = p.items || [];
    if (!menuForm.canteen_location_id && locations.value[0])
        menuForm.canteen_location_id = locations.value[0].id;
}
catch (e) {
    emit("error", msg(e));
}
finally {
    loading.value = false;
} }
async function createLocation() { try {
    await post("/canteen/locations", { ...locationForm, unit_id: locationForm.unit_id || null });
    notice.value = "Cantina cadastrada.";
    await load();
}
catch (e) {
    emit("error", msg(e));
} }
async function createMenu() { try {
    const menu = await post("/canteen/menus", { ...menuForm, starts_on: menuForm.starts_on || null, ends_on: menuForm.ends_on || null });
    for (const product of products.value.filter(x => x.product_type === 'food').slice(0, 20))
        await post(`/canteen/menus/${menu.id}/items`, { product_id: product.id });
    notice.value = "Cardápio criado; adicione/ajuste itens e publique quando estiver pronto.";
    await load();
}
catch (e) {
    emit("error", msg(e));
} }
async function publishMenu(row) { try {
    await post(`/canteen/menus/${row.id}/state`, { state: "active", reason: "Cardápio aprovado pelo gestor" });
    await load();
}
catch (e) {
    emit("error", msg(e));
} }
async function createWallet() { try {
    const w = await post("/canteen/wallets", walletForm);
    creditForm.wallet_id = w.id;
    notice.value = "Carteira criada.";
    await load();
}
catch (e) {
    emit("error", msg(e));
} }
async function credit() { try {
    await post(`/canteen/wallets/${creditForm.wallet_id}/credits`, { amount: creditForm.amount, method: creditForm.method, external_reference: creditForm.external_reference || null, reason: creditForm.reason }, `wallet-${crypto.randomUUID()}`);
    notice.value = "Recarga confirmada.";
    await load();
}
catch (e) {
    emit("error", msg(e));
} }
async function subsidy() { try {
    await post("/canteen/subsidies", { student_id: subsidyForm.student_id, subsidy_type: subsidyForm.subsidy_type, amount: subsidyForm.subsidy_type === 'fixed' ? subsidyForm.amount : null, percentage: subsidyForm.subsidy_type === 'percentage' ? subsidyForm.percentage : null, valid_from: subsidyForm.valid_from, valid_until: subsidyForm.valid_until || null, reason: subsidyForm.reason });
    notice.value = "Subsídio registrado.";
    await load();
}
catch (e) {
    emit("error", msg(e));
} }
onMounted(load);
; /* PartiallyEnd: #3632/scriptSetup.vue */
function __VLS_template() {
    const __VLS_ctx = {};
    let __VLS_components;
    let __VLS_directives;
    if (__VLS_ctx.notice) {
        __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: ("flash success") },
        });
        (__VLS_ctx.notice);
    }
    __VLS_elementAsFunction(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
        ...{ class: ("grid-2 forms") },
    });
    __VLS_elementAsFunction(__VLS_intrinsicElements.form, __VLS_intrinsicElements.form)({
        ...{ onSubmit: (__VLS_ctx.createLocation) },
        ...{ class: ("panel") },
    });
    __VLS_elementAsFunction(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.input, __VLS_intrinsicElements.input)({
        required: (true),
    });
    (__VLS_ctx.locationForm.code);
    __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.input, __VLS_intrinsicElements.input)({
        required: (true),
    });
    (__VLS_ctx.locationForm.name);
    __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
        ...{ class: ("primary") },
    });
    __VLS_elementAsFunction(__VLS_intrinsicElements.form, __VLS_intrinsicElements.form)({
        ...{ onSubmit: (__VLS_ctx.createMenu) },
        ...{ class: ("panel") },
    });
    __VLS_elementAsFunction(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.select, __VLS_intrinsicElements.select)({
        value: ((__VLS_ctx.menuForm.canteen_location_id)),
        required: (true),
    });
    for (const [x] of __VLS_getVForSourceType((__VLS_ctx.locations))) {
        __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
            value: ((x.id)),
        });
        (x.name);
    }
    __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.input, __VLS_intrinsicElements.input)({
        required: (true),
    });
    (__VLS_ctx.menuForm.name);
    __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
        ...{ class: ("cols") },
    });
    __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.input, __VLS_intrinsicElements.input)({
        type: ("date"),
    });
    (__VLS_ctx.menuForm.starts_on);
    __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.input, __VLS_intrinsicElements.input)({
        type: ("date"),
    });
    (__VLS_ctx.menuForm.ends_on);
    __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
        ...{ class: ("primary") },
    });
    __VLS_elementAsFunction(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
        ...{ class: ("grid-2 forms") },
    });
    __VLS_elementAsFunction(__VLS_intrinsicElements.form, __VLS_intrinsicElements.form)({
        ...{ onSubmit: (__VLS_ctx.createWallet) },
        ...{ class: ("panel") },
    });
    __VLS_elementAsFunction(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.select, __VLS_intrinsicElements.select)({
        value: ((__VLS_ctx.walletForm.student_id)),
        required: (true),
    });
    for (const [x] of __VLS_getVForSourceType((__VLS_ctx.students))) {
        __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
            value: ((x.id)),
        });
        (x.label);
    }
    __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
        ...{ class: ("cols") },
    });
    __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.input, __VLS_intrinsicElements.input)({
        type: ("number"),
        step: ("0.01"),
    });
    (__VLS_ctx.walletForm.daily_limit);
    __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.input, __VLS_intrinsicElements.input)({
        type: ("number"),
        step: ("0.01"),
    });
    (__VLS_ctx.walletForm.weekly_limit);
    __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
        ...{ class: ("primary") },
    });
    __VLS_elementAsFunction(__VLS_intrinsicElements.form, __VLS_intrinsicElements.form)({
        ...{ onSubmit: (__VLS_ctx.credit) },
        ...{ class: ("panel") },
    });
    __VLS_elementAsFunction(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.select, __VLS_intrinsicElements.select)({
        value: ((__VLS_ctx.creditForm.wallet_id)),
        required: (true),
    });
    for (const [x] of __VLS_getVForSourceType((__VLS_ctx.wallets))) {
        __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
            value: ((x.id)),
        });
        (x.student_name);
        (Number(x.balance).toFixed(2));
    }
    __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.input, __VLS_intrinsicElements.input)({
        type: ("number"),
        step: ("0.01"),
        min: ("0.01"),
        required: (true),
    });
    (__VLS_ctx.creditForm.amount);
    __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.input, __VLS_intrinsicElements.input)({});
    (__VLS_ctx.creditForm.external_reference);
    __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
        ...{ class: ("primary") },
    });
    __VLS_elementAsFunction(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
        ...{ class: ("grid-2 forms") },
    });
    __VLS_elementAsFunction(__VLS_intrinsicElements.form, __VLS_intrinsicElements.form)({
        ...{ onSubmit: (__VLS_ctx.subsidy) },
        ...{ class: ("panel") },
    });
    __VLS_elementAsFunction(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.select, __VLS_intrinsicElements.select)({
        value: ((__VLS_ctx.subsidyForm.student_id)),
        required: (true),
    });
    for (const [x] of __VLS_getVForSourceType((__VLS_ctx.students))) {
        __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
            value: ((x.id)),
        });
        (x.label);
    }
    __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.select, __VLS_intrinsicElements.select)({
        value: ((__VLS_ctx.subsidyForm.subsidy_type)),
    });
    __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
        value: ("fixed"),
    });
    __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
        value: ("percentage"),
    });
    __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
        value: ("free_meal"),
    });
    if (__VLS_ctx.subsidyForm.subsidy_type === 'fixed') {
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.input, __VLS_intrinsicElements.input)({
            type: ("number"),
            step: ("0.01"),
        });
        (__VLS_ctx.subsidyForm.amount);
    }
    if (__VLS_ctx.subsidyForm.subsidy_type === 'percentage') {
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.input, __VLS_intrinsicElements.input)({
            type: ("number"),
            step: ("0.01"),
        });
        (__VLS_ctx.subsidyForm.percentage);
    }
    __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
        ...{ class: ("cols") },
    });
    __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.input, __VLS_intrinsicElements.input)({
        type: ("date"),
        required: (true),
    });
    (__VLS_ctx.subsidyForm.valid_from);
    __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.input, __VLS_intrinsicElements.input)({
        type: ("date"),
    });
    (__VLS_ctx.subsidyForm.valid_until);
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
    __VLS_elementAsFunction(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
        ...{ class: ("panel") },
    });
    __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
        ...{ class: ("panel-title") },
    });
    __VLS_elementAsFunction(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
    (__VLS_ctx.menus.length);
    __VLS_elementAsFunction(__VLS_intrinsicElements.table, __VLS_intrinsicElements.table)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.thead, __VLS_intrinsicElements.thead)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.tr, __VLS_intrinsicElements.tr)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.th, __VLS_intrinsicElements.th)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.th, __VLS_intrinsicElements.th)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.th, __VLS_intrinsicElements.th)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.th, __VLS_intrinsicElements.th)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.th, __VLS_intrinsicElements.th)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.tbody, __VLS_intrinsicElements.tbody)({});
    for (const [m] of __VLS_getVForSourceType((__VLS_ctx.menus))) {
        __VLS_elementAsFunction(__VLS_intrinsicElements.tr, __VLS_intrinsicElements.tr)({
            key: ((m.id)),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
        (m.name);
        __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
        (m.starts_on || '—');
        (m.ends_on || '—');
        __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
        (m.items?.length || 0);
        __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
        (m.state);
        __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
        if (m.state === 'draft') {
            __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                ...{ onClick: (...[$event]) => {
                        if (!((m.state === 'draft')))
                            return;
                        __VLS_ctx.publishMenu(m);
                    } },
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
    (__VLS_ctx.wallets.length);
    __VLS_elementAsFunction(__VLS_intrinsicElements.table, __VLS_intrinsicElements.table)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.thead, __VLS_intrinsicElements.thead)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.tr, __VLS_intrinsicElements.tr)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.th, __VLS_intrinsicElements.th)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.th, __VLS_intrinsicElements.th)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.th, __VLS_intrinsicElements.th)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.th, __VLS_intrinsicElements.th)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.th, __VLS_intrinsicElements.th)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.tbody, __VLS_intrinsicElements.tbody)({});
    for (const [w] of __VLS_getVForSourceType((__VLS_ctx.wallets))) {
        __VLS_elementAsFunction(__VLS_intrinsicElements.tr, __VLS_intrinsicElements.tr)({
            key: ((w.id)),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
        (w.student_name);
        __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
        (Number(w.balance).toFixed(2));
        __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
        (w.daily_limit ?? '—');
        __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
        (w.weekly_limit ?? '—');
        __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
        (w.state);
    }
    ['flash', 'success', 'grid-2', 'forms', 'panel', 'primary', 'panel', 'cols', 'primary', 'grid-2', 'forms', 'panel', 'cols', 'primary', 'panel', 'primary', 'grid-2', 'forms', 'panel', 'cols', 'primary', 'panel', 'checklist', 'panel', 'panel-title', 'small', 'panel', 'panel-title',];
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
            notice: notice,
            locations: locations,
            menus: menus,
            wallets: wallets,
            students: students,
            locationForm: locationForm,
            menuForm: menuForm,
            walletForm: walletForm,
            creditForm: creditForm,
            subsidyForm: subsidyForm,
            createLocation: createLocation,
            createMenu: createMenu,
            publishMenu: publishMenu,
            createWallet: createWallet,
            credit: credit,
            subsidy: subsidy,
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
});
; /* PartiallyEnd: #4569/main.vue */
