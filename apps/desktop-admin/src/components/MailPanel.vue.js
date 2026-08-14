import { onMounted, ref } from "vue";
const props = defineProps();
const emit = defineEmits();
const busy = ref(false);
const notice = ref("");
const status = ref(null);
const messages = ref([]);
const detail = ref(null);
const folder = ref("INBOX");
const search = ref("");
const drafts = ref([]);
const moveTarget = ref("");
const compose = ref({ to: "", cc: "", bcc: "", subject: "", body_text: "" });
const composeMode = ref("new");
const sourceMessageId = ref(null);
const replyAll = ref(false);
function problem(e) {
    const x = e;
    return x.problem?.detail || x.message || "Falha no e-mail";
}
function emails(value) {
    return value
        .split(/[;,\s]+/)
        .map((x) => x.trim())
        .filter(Boolean);
}
function resetCompose() {
    compose.value = { to: "", cc: "", bcc: "", subject: "", body_text: "" };
    composeMode.value = "new";
    sourceMessageId.value = null;
    replyAll.value = false;
}
async function load() {
    busy.value = true;
    try {
        const mailboxStatus = await props.api.request("/mail/me/status");
        status.value = mailboxStatus;
        if (!(mailboxStatus.folders || []).some((f) => f.remote_name === folder.value))
            folder.value = mailboxStatus.folders?.[0]?.remote_name || "INBOX";
        await Promise.all([loadMessages(), loadDrafts()]);
    }
    catch (e) {
        status.value = null;
        emit("error", problem(e));
    }
    finally {
        busy.value = false;
    }
}
async function sync() {
    busy.value = true;
    notice.value = "";
    try {
        const r = await props.api.request("/mail/me/sync", { method: "POST" });
        notice.value = `Sincronização concluída: ${r.messages_synced || 0} mensagem(ns).`;
        await load();
    }
    catch (e) {
        emit("error", problem(e));
    }
    finally {
        busy.value = false;
    }
}
async function loadMessages() {
    try {
        const q = new URLSearchParams();
        if (folder.value)
            q.set("folder", folder.value);
        if (search.value)
            q.set("search", search.value);
        const r = await props.api.request(`/mail/me/messages?${q}`);
        messages.value = r.items || [];
    }
    catch (e) {
        emit("error", problem(e));
    }
}
async function openMessage(row) {
    try {
        detail.value = await props.api.request(`/mail/me/messages/${row.id}`);
        const flags = Array.isArray(row.flags) ? row.flags : [];
        if (!flags.includes("\\Seen")) {
            await setSeen(true, false);
        }
    }
    catch (e) {
        emit("error", problem(e));
    }
}
async function setSeen(seen, reload = true) {
    if (!detail.value?.metadata?.id)
        return;
    try {
        await props.api.request(`/mail/me/messages/${detail.value.metadata.id}/seen`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ seen }),
        });
        notice.value = seen
            ? "Mensagem marcada como lida."
            : "Mensagem marcada como não lida.";
        if (reload)
            await load();
    }
    catch (e) {
        emit("error", problem(e));
    }
}
async function moveMessage(destination) {
    if (!detail.value?.metadata?.id)
        return;
    const target = destination || moveTarget.value;
    if (!target)
        return;
    busy.value = true;
    try {
        await props.api.request(`/mail/me/messages/${detail.value.metadata.id}/move`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ destination_folder: target }),
        });
        notice.value = `Mensagem movida para ${target}.`;
        detail.value = null;
        await load();
    }
    catch (e) {
        emit("error", problem(e));
    }
    finally {
        busy.value = false;
    }
}
async function trash() {
    if (!detail.value?.metadata?.id)
        return;
    busy.value = true;
    try {
        await props.api.request(`/mail/me/messages/${detail.value.metadata.id}/trash`, { method: "POST" });
        notice.value = "Mensagem movida para a lixeira.";
        detail.value = null;
        await load();
    }
    catch (e) {
        emit("error", problem(e));
    }
    finally {
        busy.value = false;
    }
}
function beginReply(all = false) {
    if (!detail.value)
        return;
    const m = detail.value.metadata || {};
    const sender = JSON.parse(m.sender_json || "{}");
    composeMode.value = "reply";
    sourceMessageId.value = m.id;
    replyAll.value = all;
    compose.value = {
        to: sender.email || "",
        cc: "",
        bcc: "",
        subject: m.subject || "",
        body_text: "",
    };
}
function beginForward() {
    if (!detail.value)
        return;
    const m = detail.value.metadata || {};
    composeMode.value = "forward";
    sourceMessageId.value = m.id;
    replyAll.value = false;
    compose.value = {
        to: "",
        cc: "",
        bcc: "",
        subject: m.subject || "",
        body_text: "",
    };
}
async function send() {
    busy.value = true;
    try {
        const key = `mail-${crypto.randomUUID()}`;
        if (composeMode.value === "reply" && sourceMessageId.value) {
            await props.api.request(`/mail/me/messages/${sourceMessageId.value}/reply`, {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                    "Idempotency-Key": key,
                },
                body: JSON.stringify({
                    body_text: compose.value.body_text,
                    reply_all: replyAll.value,
                }),
            });
        }
        else if (composeMode.value === "forward" && sourceMessageId.value) {
            await props.api.request(`/mail/me/messages/${sourceMessageId.value}/forward`, {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                    "Idempotency-Key": key,
                },
                body: JSON.stringify({
                    to: emails(compose.value.to),
                    cc: emails(compose.value.cc),
                    bcc: emails(compose.value.bcc),
                    subject: compose.value.subject,
                    body_text: compose.value.body_text,
                }),
            });
        }
        else {
            await props.api.request("/mail/me/send", {
                method: "POST",
                headers: { "Content-Type": "application/json", "Idempotency-Key": key },
                body: JSON.stringify({
                    to: emails(compose.value.to),
                    cc: emails(compose.value.cc),
                    bcc: emails(compose.value.bcc),
                    subject: compose.value.subject,
                    body_text: compose.value.body_text,
                }),
            });
        }
        notice.value = "Mensagem enviada.";
        resetCompose();
    }
    catch (e) {
        emit("error", problem(e));
    }
    finally {
        busy.value = false;
    }
}
async function saveDraft() {
    busy.value = true;
    try {
        await props.api.request("/mail/me/drafts", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                to: emails(compose.value.to),
                cc: emails(compose.value.cc),
                bcc: emails(compose.value.bcc),
                subject: compose.value.subject,
                body_text: compose.value.body_text,
            }),
        });
        notice.value = "Rascunho salvo.";
        await loadDrafts();
    }
    catch (e) {
        emit("error", problem(e));
    }
    finally {
        busy.value = false;
    }
}
async function loadDrafts() {
    try {
        const r = await props.api.request("/mail/me/drafts");
        drafts.value = r.items || [];
    }
    catch {
        drafts.value = [];
    }
}
async function sendDraft(row) {
    busy.value = true;
    try {
        await props.api.request(`/mail/me/drafts/${row.id}/send`, {
            method: "POST",
            headers: { "Idempotency-Key": `draft-${row.id}-${row.version}` },
        });
        notice.value = "Rascunho enviado.";
        await loadDrafts();
    }
    catch (e) {
        emit("error", problem(e));
    }
    finally {
        busy.value = false;
    }
}
async function downloadAttachment(index, item) {
    if (!detail.value?.metadata?.id)
        return;
    try {
        const response = await props.api.response(`/mail/me/messages/${detail.value.metadata.id}/attachments/${index}`, { headers: { Accept: item.content_type || "application/octet-stream" } });
        const blob = await response.blob();
        const expected = response.headers.get("x-content-sha256");
        if (expected && crypto.subtle) {
            const digest = Array.from(new Uint8Array(await crypto.subtle.digest("SHA-256", await blob.arrayBuffer())))
                .map((v) => v.toString(16).padStart(2, "0"))
                .join("");
            if (digest !== expected)
                throw new Error("Integridade SHA-256 do anexo inválida");
        }
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = item.filename || `anexo-${index + 1}`;
        a.click();
        setTimeout(() => URL.revokeObjectURL(url), 1000);
    }
    catch (e) {
        emit("error", problem(e));
    }
}
onMounted(load);
; /* PartiallyEnd: #3632/scriptSetup.vue */
function __VLS_template() {
    const __VLS_ctx = {};
    let __VLS_components;
    let __VLS_directives;
    ['mail-folders', 'mail-folders', 'mail-folders', 'mail-folders', 'mail-search', 'mail-item', 'mail-item', 'mail-item', 'reader-actions', 'reader-actions', 'attachment', 'mail-compose', 'mail-grid', 'mail-reader', 'mail-compose', 'mail-grid', 'mail-reader', 'mail-compose', 'mail-toolbar',];
    // CSS variable injection 
    // CSS variable injection end 
    __VLS_elementAsFunction(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
        ...{ class: ("mail-layout") },
    });
    if (__VLS_ctx.notice) {
        __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: ("mail-ok") },
        });
        (__VLS_ctx.notice);
    }
    __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
        ...{ class: ("mail-toolbar panel") },
    });
    __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
    if (__VLS_ctx.status) {
        __VLS_elementAsFunction(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
        (__VLS_ctx.status.account?.email);
        (__VLS_ctx.status.account?.last_sync_at
            ? new Date(__VLS_ctx.status.account.last_sync_at).toLocaleString("pt-BR")
            : "ainda não sincronizado");
    }
    __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
        ...{ class: ("mail-actions") },
    });
    __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
        ...{ onClick: (__VLS_ctx.sync) },
        disabled: ((__VLS_ctx.busy)),
    });
    __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
        ...{ onClick: (__VLS_ctx.load) },
        disabled: ((__VLS_ctx.busy)),
    });
    if (!__VLS_ctx.status) {
        __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: ("panel") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.h3, __VLS_intrinsicElements.h3)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({});
    }
    else {
        __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: ("mail-grid") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.aside, __VLS_intrinsicElements.aside)({
            ...{ class: ("panel mail-folders") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.h3, __VLS_intrinsicElements.h3)({});
        for (const [f] of __VLS_getVForSourceType((__VLS_ctx.status.folders || []))) {
            __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                ...{ onClick: (...[$event]) => {
                        if (!(!((!__VLS_ctx.status))))
                            return;
                        __VLS_ctx.folder = f.remote_name;
                        __VLS_ctx.detail = null;
                        __VLS_ctx.loadMessages();
                        ;
                    } },
                key: ((f.id)),
                ...{ class: (({ active: __VLS_ctx.folder === f.remote_name })) },
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
            (f.display_name);
            if (f.unread_count) {
                __VLS_elementAsFunction(__VLS_intrinsicElements.b, __VLS_intrinsicElements.b)({});
                (f.unread_count);
            }
        }
        __VLS_elementAsFunction(__VLS_intrinsicElements.hr)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.h3, __VLS_intrinsicElements.h3)({});
        for (const [d] of __VLS_getVForSourceType((__VLS_ctx.drafts))) {
            __VLS_elementAsFunction(__VLS_intrinsicElements.article, __VLS_intrinsicElements.article)({
                key: ((d.id)),
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
            (d.subject || "(sem assunto)");
            __VLS_elementAsFunction(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
            (d.version);
            __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                ...{ onClick: (...[$event]) => {
                        if (!(!((!__VLS_ctx.status))))
                            return;
                        __VLS_ctx.sendDraft(d);
                    } },
            });
        }
        __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: ("panel mail-list") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: ("mail-search") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.input)({
            ...{ onKeyup: (__VLS_ctx.loadMessages) },
            placeholder: ("Pesquisar assunto ou prévia"),
        });
        (__VLS_ctx.search);
        __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
            ...{ onClick: (__VLS_ctx.loadMessages) },
        });
        for (const [m] of __VLS_getVForSourceType((__VLS_ctx.messages))) {
            __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                ...{ onClick: (...[$event]) => {
                        if (!(!((!__VLS_ctx.status))))
                            return;
                        __VLS_ctx.openMessage(m);
                    } },
                ...{ class: ("mail-item") },
                key: ((m.id)),
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
            (m.sender?.name || m.sender?.email || "Remetente");
            __VLS_elementAsFunction(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
            (m.subject || "(sem assunto)");
            __VLS_elementAsFunction(__VLS_intrinsicElements.em, __VLS_intrinsicElements.em)({});
            (m.preview);
            __VLS_elementAsFunction(__VLS_intrinsicElements.time, __VLS_intrinsicElements.time)({});
            (m.received_at
                ? new Date(m.received_at).toLocaleString("pt-BR")
                : "");
        }
        if (!__VLS_ctx.messages.length) {
            __VLS_elementAsFunction(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({});
        }
        if (__VLS_ctx.detail) {
            __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: ("panel mail-reader") },
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.header, __VLS_intrinsicElements.header)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.h3, __VLS_intrinsicElements.h3)({});
            (__VLS_ctx.detail.content?.subject || __VLS_ctx.detail.metadata?.subject);
            __VLS_elementAsFunction(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
            (__VLS_ctx.detail.content?.sender?.name);
            (__VLS_ctx.detail.content?.sender?.email);
            __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: ("reader-actions") },
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                ...{ onClick: (...[$event]) => {
                        if (!(!((!__VLS_ctx.status))))
                            return;
                        if (!((__VLS_ctx.detail)))
                            return;
                        __VLS_ctx.beginReply(false);
                    } },
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                ...{ onClick: (...[$event]) => {
                        if (!(!((!__VLS_ctx.status))))
                            return;
                        if (!((__VLS_ctx.detail)))
                            return;
                        __VLS_ctx.beginReply(true);
                    } },
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                ...{ onClick: (__VLS_ctx.beginForward) },
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                ...{ onClick: (...[$event]) => {
                        if (!(!((!__VLS_ctx.status))))
                            return;
                        if (!((__VLS_ctx.detail)))
                            return;
                        __VLS_ctx.setSeen(false);
                    } },
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.select, __VLS_intrinsicElements.select)({
                value: ((__VLS_ctx.moveTarget)),
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
                value: (""),
            });
            for (const [f] of __VLS_getVForSourceType((__VLS_ctx.status.folders || []))) {
                __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
                    key: ((f.id)),
                    value: ((f.remote_name)),
                });
                (f.display_name);
            }
            __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                ...{ onClick: (...[$event]) => {
                        if (!(!((!__VLS_ctx.status))))
                            return;
                        if (!((__VLS_ctx.detail)))
                            return;
                        __VLS_ctx.moveMessage();
                    } },
                disabled: ((!__VLS_ctx.moveTarget)),
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                ...{ onClick: (__VLS_ctx.trash) },
                ...{ class: ("danger") },
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.pre, __VLS_intrinsicElements.pre)({});
            (__VLS_ctx.detail.content?.text);
            if (__VLS_ctx.detail.content?.attachments?.length) {
                __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({});
                __VLS_elementAsFunction(__VLS_intrinsicElements.h4, __VLS_intrinsicElements.h4)({});
                for (const [a, i] of __VLS_getVForSourceType((__VLS_ctx.detail.content.attachments))) {
                    __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                        ...{ onClick: (...[$event]) => {
                                if (!(!((!__VLS_ctx.status))))
                                    return;
                                if (!((__VLS_ctx.detail)))
                                    return;
                                if (!((__VLS_ctx.detail.content?.attachments?.length)))
                                    return;
                                __VLS_ctx.downloadAttachment(i, a);
                            } },
                        ...{ class: ("attachment") },
                        key: ((a.sha256)),
                    });
                    (a.filename);
                    (a.size_bytes);
                    (a.sha256);
                }
            }
        }
        __VLS_elementAsFunction(__VLS_intrinsicElements.form, __VLS_intrinsicElements.form)({
            ...{ onSubmit: (__VLS_ctx.send) },
            ...{ class: ("panel mail-compose") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.h3, __VLS_intrinsicElements.h3)({});
        (__VLS_ctx.composeMode === "reply"
            ? "Responder"
            : __VLS_ctx.composeMode === "forward"
                ? "Encaminhar"
                : "Nova mensagem");
        if (__VLS_ctx.composeMode !== 'new') {
            __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                ...{ onClick: (__VLS_ctx.resetCompose) },
                type: ("button"),
            });
            (__VLS_ctx.composeMode === "reply" ? "resposta" : "encaminhamento");
        }
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.input)({
            required: ((__VLS_ctx.composeMode !== 'reply')),
            placeholder: ("destino@escola.com.br"),
            disabled: ((__VLS_ctx.composeMode === 'reply')),
        });
        (__VLS_ctx.compose.to);
        if (__VLS_ctx.composeMode !== 'reply') {
            __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.input)({});
            (__VLS_ctx.compose.cc);
        }
        if (__VLS_ctx.composeMode !== 'reply') {
            __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.input)({});
            (__VLS_ctx.compose.bcc);
        }
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.input)({
            disabled: ((__VLS_ctx.composeMode === 'reply')),
        });
        (__VLS_ctx.compose.subject);
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.textarea, __VLS_intrinsicElements.textarea)({
            value: ((__VLS_ctx.compose.body_text)),
            rows: ("10"),
            required: (true),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: ("mail-actions") },
        });
        if (__VLS_ctx.composeMode === 'new') {
            __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                ...{ onClick: (__VLS_ctx.saveDraft) },
                type: ("button"),
            });
        }
        __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
            ...{ class: ("primary") },
            disabled: ((__VLS_ctx.busy)),
        });
    }
    ['mail-layout', 'mail-ok', 'mail-toolbar', 'panel', 'mail-actions', 'panel', 'mail-grid', 'panel', 'mail-folders', 'active', 'panel', 'mail-list', 'mail-search', 'mail-item', 'panel', 'mail-reader', 'reader-actions', 'danger', 'attachment', 'panel', 'mail-compose', 'mail-actions', 'primary',];
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
            busy: busy,
            notice: notice,
            status: status,
            messages: messages,
            detail: detail,
            folder: folder,
            search: search,
            drafts: drafts,
            moveTarget: moveTarget,
            compose: compose,
            composeMode: composeMode,
            resetCompose: resetCompose,
            load: load,
            sync: sync,
            loadMessages: loadMessages,
            openMessage: openMessage,
            setSeen: setSeen,
            moveMessage: moveMessage,
            trash: trash,
            beginReply: beginReply,
            beginForward: beginForward,
            send: send,
            saveDraft: saveDraft,
            sendDraft: sendDraft,
            downloadAttachment: downloadAttachment,
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
