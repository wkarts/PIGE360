import { computed, onMounted, reactive, ref } from "vue";
import { Pige360SessionClient } from "@pige360/auth";
const api = new Pige360SessionClient();
const ready = ref(false), auth = ref(false), busy = ref(false), error = ref(""), notice = ref("");
const email = ref(""), password = ref("");
const brand = ref({});
const products = ref([]), sales = ref([]), cash = ref(null);
const locations = ref([]), students = ref([]), quote = ref(null);
const mode = ref("pos"), selectedLocation = ref(""), selectedStudent = ref(""), studentQuery = ref("");
const query = ref(""), payment = ref("pix");
const cart = reactive({});
const school = computed(() => brand.value.short_name || brand.value.trade_name || brand.value.legal_name || "Instituição");
const visibleProducts = computed(() => products.value.filter(p => !query.value || `${p.name} ${p.sku} ${p.barcode || ""}`.toLowerCase().includes(query.value.toLowerCase())));
const cartLines = computed(() => products.value.filter(p => (cart[p.id] || 0) > 0).map(p => ({ ...p, quantity: cart[p.id] || 0, line: Number(p.sale_price) * (cart[p.id] || 0) })));
const grossTotal = computed(() => cartLines.value.reduce((a, b) => a + b.line, 0));
const dueTotal = computed(() => mode.value === "canteen" && quote.value ? Number(quote.value.customer_due || 0) : grossTotal.value);
const selectedStudentRow = computed(() => students.value.find(x => x.id === selectedStudent.value));
function msg(e) { const p = e?.problem; return p?.detail || (e instanceof Error ? e.message : "Erro inesperado"); }
function apply() { document.documentElement.style.setProperty("--brand-primary", brand.value.primary_color || "#006D77"); document.documentElement.style.setProperty("--brand-secondary", brand.value.secondary_color || "#0D1B2A"); document.title = `${school.value} — PDV`; }
function invalidateQuote() { quote.value = null; }
async function loadStudents() { if (mode.value !== "canteen")
    return; const q = studentQuery.value.trim(); students.value = (await api.request(`/canteen/pos/students${q ? `?q=${encodeURIComponent(q)}` : ""}`)).items || []; }
async function load() { brand.value = await api.request("/branding/current"); apply(); products.value = (await api.request("/products")).items || []; sales.value = (await api.request("/sales")).items || []; locations.value = (await api.request("/canteen/locations")).items || []; const sessions = (await api.request("/pos/cash-sessions?state=open")).items || []; cash.value = sessions.find((x) => x.operator_user_id === api.claims()?.sub) || sessions[0] || null; await loadStudents(); }
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
async function login() { busy.value = true; error.value = ""; try {
    await api.login(email.value, password.value);
    auth.value = true;
    await load();
}
catch (e) {
    error.value = msg(e);
}
finally {
    busy.value = false;
} }
async function logout() { await api.logout(); auth.value = false; }
async function openCash() { try {
    cash.value = await api.request("/pos/cash-sessions/open", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ terminal_code: "PDV-01", opening_amount: "0.00" }) });
    notice.value = "Caixa aberto.";
}
catch (e) {
    error.value = msg(e);
} }
function add(p) { cart[p.id] = (cart[p.id] || 0) + 1; invalidateQuote(); }
function remove(p) { cart[p.id] = Math.max(0, (cart[p.id] || 0) - 1); invalidateQuote(); }
function changeMode() { invalidateQuote(); if (mode.value === "pos") {
    selectedLocation.value = "";
    selectedStudent.value = "";
    payment.value = "pix";
}
else {
    payment.value = "wallet";
    void loadStudents();
} }
async function calculateQuote() {
    error.value = "";
    if (mode.value !== "canteen")
        return null;
    if (!selectedLocation.value || !selectedStudent.value) {
        error.value = "Selecione a cantina e o aluno antes de calcular a venda.";
        return null;
    }
    if (!cartLines.value.length) {
        error.value = "Adicione pelo menos um produto.";
        return null;
    }
    try {
        quote.value = await api.request("/canteen/quote", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ canteen_location_id: selectedLocation.value, student_id: selectedStudent.value, items: cartLines.value.map(x => ({ product_id: x.id, quantity: String(x.quantity) })) }) });
        return quote.value;
    }
    catch (e) {
        quote.value = null;
        error.value = msg(e);
        return null;
    }
}
async function sell() {
    if (!cash.value) {
        error.value = "Abra o caixa antes de vender.";
        return;
    }
    if (!cartLines.value.length)
        return;
    busy.value = true;
    error.value = "";
    try {
        const q = mode.value === "canteen" ? await calculateQuote() : null;
        if (mode.value === "canteen" && !q)
            return;
        const due = mode.value === "canteen" ? Number(q?.customer_due || 0) : grossTotal.value;
        const payments = due > 0 ? [{ method: payment.value, amount: due.toFixed(2) }] : [];
        await api.request("/sales", { method: "POST", headers: { "Content-Type": "application/json", "Idempotency-Key": `pdv-${crypto.randomUUID()}` }, body: JSON.stringify({ cash_session_id: cash.value.id, channel: mode.value, canteen_location_id: mode.value === "canteen" ? selectedLocation.value : null, student_id: mode.value === "canteen" ? selectedStudent.value : null, items: cartLines.value.map(x => ({ product_id: x.id, quantity: String(x.quantity), discount: "0" })), payments, discount: "0", request_fiscal_document: true }) });
        Object.keys(cart).forEach(k => delete cart[k]);
        quote.value = null;
        notice.value = mode.value === "canteen" ? "Venda da cantina concluída com políticas, carteira, estoque e fiscal integrados." : "Venda concluída e integrada ao estoque/financeiro/fiscal.";
        await load();
    }
    catch (e) {
        error.value = msg(e);
    }
    finally {
        busy.value = false;
    }
}
async function closeCash() { if (!cash.value)
    return; try {
    await api.request(`/pos/cash-sessions/${cash.value.id}/close`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ closing_amount: "0.00", reason: "Fechamento operacional do terminal" }) });
    cash.value = null;
    notice.value = "Caixa fechado.";
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
            disabled: ((__VLS_ctx.busy)),
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
        (__VLS_ctx.school);
        __VLS_elementAsFunction(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({
            ...{ class: ("cash-state") },
        });
        (__VLS_ctx.cash ? 'Caixa aberto' : 'Caixa fechado');
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
        __VLS_elementAsFunction(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
            ...{ class: ("toolbar") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.select, __VLS_intrinsicElements.select)({
            ...{ onChange: (__VLS_ctx.changeMode) },
            value: ((__VLS_ctx.mode)),
            ...{ class: ("mode-select") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
            value: ("pos"),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
            value: ("canteen"),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.input, __VLS_intrinsicElements.input)({
            placeholder: ("Buscar produto, SKU ou código de barras"),
        });
        (__VLS_ctx.query);
        if (!__VLS_ctx.cash) {
            __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                ...{ onClick: (__VLS_ctx.openCash) },
                ...{ class: ("primary") },
            });
        }
        else {
            __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                ...{ onClick: (__VLS_ctx.closeCash) },
                ...{ class: ("ghost-dark") },
            });
        }
        if (__VLS_ctx.mode === 'canteen') {
            __VLS_elementAsFunction(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
                ...{ class: ("panel canteen-context") },
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: ("section-title") },
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: ("context-grid") },
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.select, __VLS_intrinsicElements.select)({
                ...{ onChange: (__VLS_ctx.invalidateQuote) },
                value: ((__VLS_ctx.selectedLocation)),
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
                value: (""),
            });
            for (const [l] of __VLS_getVForSourceType((__VLS_ctx.locations))) {
                __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
                    key: ((l.id)),
                    value: ((l.id)),
                });
                (l.name);
            }
            __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: ("student-search") },
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.input, __VLS_intrinsicElements.input)({
                ...{ onKeyup: (__VLS_ctx.loadStudents) },
                placeholder: ("Nome ou matrícula"),
            });
            (__VLS_ctx.studentQuery);
            __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                ...{ onClick: (__VLS_ctx.loadStudents) },
                ...{ class: ("ghost-dark") },
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.select, __VLS_intrinsicElements.select)({
                ...{ onChange: (__VLS_ctx.invalidateQuote) },
                value: ((__VLS_ctx.selectedStudent)),
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
                value: (""),
            });
            for (const [s] of __VLS_getVForSourceType((__VLS_ctx.students))) {
                __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
                    key: ((s.id)),
                    value: ((s.id)),
                });
                (s.social_name || s.full_name);
                (s.registration_number);
            }
            if (__VLS_ctx.selectedStudentRow) {
                __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                    ...{ class: ("wallet-chip") },
                });
                __VLS_elementAsFunction(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
                (__VLS_ctx.selectedStudentRow.wallet_balance == null ? 'não cadastrada' : `R$ ${Number(__VLS_ctx.selectedStudentRow.wallet_balance).toFixed(2)}`);
            }
        }
        __VLS_elementAsFunction(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
            ...{ class: ("pos-grid") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: ("panel") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: ("section-title") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
        (__VLS_ctx.visibleProducts.length);
        __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: ("product-grid") },
        });
        for (const [p] of __VLS_getVForSourceType((__VLS_ctx.visibleProducts))) {
            __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                ...{ onClick: (...[$event]) => {
                        if (!(!((!__VLS_ctx.ready))))
                            return;
                        if (!(!((!__VLS_ctx.auth))))
                            return;
                        __VLS_ctx.add(p);
                    } },
                key: ((p.id)),
                ...{ class: ("product") },
                disabled: ((Number(p.stock_quantity) <= 0)),
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
            (p.name);
            __VLS_elementAsFunction(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
            (p.sku);
            (p.stock_quantity);
            __VLS_elementAsFunction(__VLS_intrinsicElements.b, __VLS_intrinsicElements.b)({});
            (Number(p.sale_price).toFixed(2));
        }
        __VLS_elementAsFunction(__VLS_intrinsicElements.aside, __VLS_intrinsicElements.aside)({
            ...{ class: ("panel cart") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: ("section-title") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
        (__VLS_ctx.cartLines.length);
        for (const [line] of __VLS_getVForSourceType((__VLS_ctx.cartLines))) {
            __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                key: ((line.id)),
                ...{ class: ("cart-line") },
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
            (line.name);
            __VLS_elementAsFunction(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
            (Number(line.sale_price).toFixed(2));
            (line.quantity);
            __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: ("qty") },
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                ...{ onClick: (...[$event]) => {
                        if (!(!((!__VLS_ctx.ready))))
                            return;
                        if (!(!((!__VLS_ctx.auth))))
                            return;
                        __VLS_ctx.remove(line);
                    } },
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
            (line.quantity);
            __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                ...{ onClick: (...[$event]) => {
                        if (!(!((!__VLS_ctx.ready))))
                            return;
                        if (!(!((!__VLS_ctx.auth))))
                            return;
                        __VLS_ctx.add(line);
                    } },
            });
        }
        if (!__VLS_ctx.cartLines.length) {
            __VLS_elementAsFunction(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({
                ...{ class: ("empty") },
            });
        }
        if (__VLS_ctx.mode === 'canteen') {
            __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: ("quote-box") },
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                ...{ onClick: (__VLS_ctx.calculateQuote) },
                ...{ class: ("ghost-dark") },
                disabled: ((!__VLS_ctx.cartLines.length)),
            });
            if (__VLS_ctx.quote) {
                __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({});
                __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
                __VLS_elementAsFunction(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
                (Number(__VLS_ctx.quote.total_amount).toFixed(2));
                __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({});
                __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
                __VLS_elementAsFunction(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
                (Number(__VLS_ctx.quote.subsidy_amount).toFixed(2));
                __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                    ...{ class: ("due") },
                });
                __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
                __VLS_elementAsFunction(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
                (Number(__VLS_ctx.quote.customer_due).toFixed(2));
                __VLS_elementAsFunction(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
                (__VLS_ctx.quote.wallet_balance == null ? 'não cadastrada' : `R$ ${Number(__VLS_ctx.quote.wallet_balance).toFixed(2)}`);
                (Number(__VLS_ctx.quote.daily_spent || 0).toFixed(2));
            }
        }
        else {
            __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: ("total") },
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
            (__VLS_ctx.grossTotal.toFixed(2));
        }
        if (__VLS_ctx.dueTotal > 0) {
            __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.select, __VLS_intrinsicElements.select)({
                value: ((__VLS_ctx.payment)),
            });
            if (__VLS_ctx.mode === 'canteen') {
                __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
                    value: ("wallet"),
                });
            }
            __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
                value: ("pix"),
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
                value: ("cash"),
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
                value: ("card"),
            });
        }
        else if (__VLS_ctx.mode === 'canteen' && __VLS_ctx.quote) {
            __VLS_elementAsFunction(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({
                ...{ class: ("free-meal") },
            });
        }
        __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
            ...{ onClick: (__VLS_ctx.sell) },
            ...{ class: ("primary") },
            disabled: ((__VLS_ctx.busy || !__VLS_ctx.cash || !__VLS_ctx.cartLines.length)),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
            ...{ class: ("panel") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: ("section-title") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
        for (const [s] of __VLS_getVForSourceType((__VLS_ctx.sales.slice(0, 10)))) {
            __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: ("list-row") },
                key: ((s.id)),
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
            (s.id.slice(-8));
            __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
            (s.channel);
            (s.state);
            __VLS_elementAsFunction(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
            (Number(s.total_amount).toFixed(2));
        }
    }
    ['center', 'login-page', 'login-card', 'mark', 'eyebrow', 'flash', 'error', 'primary', 'mobile-shell', 'brand', 'mark', 'cash-state', 'ghost', 'flash', 'error', 'flash', 'success', 'toolbar', 'mode-select', 'primary', 'ghost-dark', 'panel', 'canteen-context', 'section-title', 'context-grid', 'student-search', 'ghost-dark', 'wallet-chip', 'pos-grid', 'panel', 'section-title', 'product-grid', 'product', 'panel', 'cart', 'section-title', 'cart-line', 'qty', 'empty', 'quote-box', 'ghost-dark', 'due', 'total', 'free-meal', 'primary', 'panel', 'section-title', 'list-row',];
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
            sales: sales,
            cash: cash,
            locations: locations,
            students: students,
            quote: quote,
            mode: mode,
            selectedLocation: selectedLocation,
            selectedStudent: selectedStudent,
            studentQuery: studentQuery,
            query: query,
            payment: payment,
            school: school,
            visibleProducts: visibleProducts,
            cartLines: cartLines,
            grossTotal: grossTotal,
            dueTotal: dueTotal,
            selectedStudentRow: selectedStudentRow,
            invalidateQuote: invalidateQuote,
            loadStudents: loadStudents,
            login: login,
            logout: logout,
            openCash: openCash,
            add: add,
            remove: remove,
            changeMode: changeMode,
            calculateQuote: calculateQuote,
            sell: sell,
            closeCash: closeCash,
        };
    },
});
export default (await import('vue')).defineComponent({
    setup() {
        return {};
    },
});
; /* PartiallyEnd: #4569/main.vue */
