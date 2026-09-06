import { computed, onMounted, reactive, ref, watch } from "vue";
const props = defineProps();
const emit = defineEmits();
const loading = ref(false);
const agents = ref([]);
const providers = ref([]);
const jobs = ref([]);
const includeRevoked = ref(false);
const oneTimeCredential = ref(null);
const queueReceipt = ref(null);
const agentRevokeReason = ref("");
const jobCancelReason = ref("");
const canManageAgents = computed(() => Boolean(props.api.claims()?.roles?.includes("platform_super_admin")));
const operationalSummary = computed(() => ({
    activeAgents: agents.value.filter((agent) => agent.state === "active").length,
    onlineAgents: agents.value.filter((agent) => agent.connectivity === "online").length,
    configuredProviders: providers.value.filter((provider) => provider.configured).length,
    queuedJobs: jobs.value.filter((job) => job.state === "queued").length,
    runningJobs: jobs.value.filter((job) => job.state === "running").length,
    attentionJobs: jobs.value.filter((job) => job.attention_required).length,
}));
const agentForm = reactive({
    name: "",
    agent_type: "multi",
    capabilities: ["backup.execute", "restore.execute", "deploy.execute"],
    software_version: "",
    reason: "",
});
const jobForm = reactive({
    operation_type: "backup",
    resource_scope: "platform",
    tenant_id: "",
    deployment_target: "cloudpanel",
    image_mode: "registry",
    release_version: "",
    backup_reference: "",
    reason: "",
});
const jobFilters = reactive({ operation_type: "", state: "", tenant_id: "" });
const capabilityOptions = [
    ["backup.execute", "Executar backup"],
    ["restore.execute", "Executar restore"],
    ["deploy.execute", "Executar deploy"],
];
function message(error) {
    const candidate = error;
    return candidate?.problem?.detail || candidate?.message || "Erro inesperado";
}
function idempotencyKey(scope) {
    return `${scope}:${crypto.randomUUID()}`;
}
function tenantName(tenantId) {
    if (!tenantId)
        return "Plataforma";
    const tenant = props.tenants.find((item) => item.id === tenantId);
    return tenant ? `${tenant.trade_name} (${tenant.code})` : tenantId;
}
function providerState(state) {
    return {
        configured_not_probed: "Configurado — não testado externamente",
        configuration_incomplete: "Configuração incompleta",
        local_fallback: "Fallback local",
        disabled: "Desabilitado",
    }[state] || state;
}
function connectivityLabel(state) {
    return {
        registered: "Registrado — aguardando heartbeat",
        online: "Online",
        stale: "Sem heartbeat recente",
        revoked: "Revogado",
    }[state] || state;
}
async function loadAgents() {
    const data = await props.api.request(`/platform/operations/agents?include_revoked=${includeRevoked.value ? "true" : "false"}`);
    agents.value = data.items || [];
}
async function loadProviders() {
    const data = await props.api.request("/platform/operations/providers");
    providers.value = data.items || [];
}
async function loadJobs() {
    const params = new URLSearchParams({ limit: "100" });
    if (jobFilters.operation_type)
        params.set("operation_type", jobFilters.operation_type);
    if (jobFilters.state)
        params.set("state", jobFilters.state);
    if (jobFilters.tenant_id)
        params.set("tenant_id", jobFilters.tenant_id);
    const data = await props.api.request(`/platform/operations/jobs?${params.toString()}`);
    jobs.value = data.items || [];
}
async function loadAll() {
    loading.value = true;
    try {
        await Promise.all([loadAgents(), loadProviders(), loadJobs()]);
    }
    catch (error) {
        emit("feedback", { type: "error", message: message(error) });
    }
    finally {
        loading.value = false;
    }
}
function registrationCapabilities() {
    const required = {
        backup: "backup.execute",
        restore: "restore.execute",
        deploy: "deploy.execute",
    }[agentForm.agent_type];
    return required ? [required] : [...new Set(agentForm.capabilities)].sort();
}
async function registerAgent() {
    if (!canManageAgents.value)
        return;
    const capabilities = registrationCapabilities();
    if (!capabilities.length) {
        emit("feedback", { type: "error", message: "Selecione ao menos uma capability para o agente." });
        return;
    }
    try {
        const result = await props.api.request("/platform/operations/agents", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                name: agentForm.name,
                agent_type: agentForm.agent_type,
                capabilities,
                software_version: agentForm.software_version || null,
                reason: agentForm.reason,
            }),
        });
        oneTimeCredential.value = result.credential;
        Object.assign(agentForm, {
            name: "",
            agent_type: "multi",
            capabilities: ["backup.execute", "restore.execute", "deploy.execute"],
            software_version: "",
            reason: "",
        });
        emit("feedback", { type: "success", message: "Agente registrado. Guarde agora a credencial exibida uma única vez." });
        await loadAgents();
    }
    catch (error) {
        emit("feedback", { type: "error", message: message(error) });
    }
}
async function copyCredential() {
    if (!oneTimeCredential.value?.token)
        return;
    try {
        await navigator.clipboard.writeText(String(oneTimeCredential.value.token));
        emit("feedback", { type: "success", message: "Credencial copiada. Armazene-a em um secret manager." });
    }
    catch {
        emit("feedback", { type: "error", message: "Não foi possível copiar automaticamente a credencial." });
    }
}
async function revokeAgent(agent) {
    if (!canManageAgents.value)
        return;
    if (agentRevokeReason.value.trim().length < 10) {
        emit("feedback", { type: "error", message: "Informe um motivo auditável para revogar o agente." });
        return;
    }
    try {
        await props.api.request(`/platform/operations/agents/${agent.id}/revoke`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ expected_version: agent.version, reason: agentRevokeReason.value }),
        });
        agentRevokeReason.value = "";
        emit("feedback", { type: "success", message: "Agente revogado. Jobs ativos continuam marcados para atenção manual." });
        await Promise.all([loadAgents(), loadJobs()]);
    }
    catch (error) {
        emit("feedback", { type: "error", message: message(error) });
    }
}
function operationalJobPayload() {
    const payload = {
        operation_type: jobForm.operation_type,
        resource_scope: jobForm.operation_type === "deploy" ? "platform" : jobForm.resource_scope,
        reason: jobForm.reason,
    };
    if (payload.resource_scope === "tenant")
        payload.tenant_id = jobForm.tenant_id;
    if (jobForm.operation_type === "restore")
        payload.backup_reference = jobForm.backup_reference;
    if (jobForm.operation_type === "deploy") {
        payload.deployment_target = jobForm.deployment_target;
        payload.image_mode = jobForm.image_mode;
        payload.release_version = jobForm.release_version;
    }
    return payload;
}
async function queueJob() {
    try {
        const result = await props.api.request("/platform/operations/jobs", {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                "Idempotency-Key": idempotencyKey(`ops-${jobForm.operation_type}`),
            },
            body: JSON.stringify(operationalJobPayload()),
        });
        queueReceipt.value = {
            id: result.job?.id,
            execution_started: Boolean(result.execution_started),
            replayed: Boolean(result.replayed),
        };
        jobForm.reason = "";
        emit("feedback", {
            type: "success",
            message: result.execution_started
                ? "Job aceito e execução iniciada."
                : "Job registrado na fila; a execução ainda não começou.",
        });
        await loadJobs();
    }
    catch (error) {
        emit("feedback", { type: "error", message: message(error) });
    }
}
async function cancelJob(job) {
    if (jobCancelReason.value.trim().length < 10) {
        emit("feedback", { type: "error", message: "Informe um motivo auditável para cancelar o job." });
        return;
    }
    try {
        await props.api.request(`/platform/operations/jobs/${job.id}/cancel`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ expected_version: job.version, reason: jobCancelReason.value }),
        });
        jobCancelReason.value = "";
        emit("feedback", { type: "success", message: "Job ainda não reivindicado foi cancelado." });
        await loadJobs();
    }
    catch (error) {
        emit("feedback", { type: "error", message: message(error) });
    }
}
watch(() => agentForm.agent_type, (agentType) => {
    const capability = {
        backup: "backup.execute",
        restore: "restore.execute",
        deploy: "deploy.execute",
    }[agentType];
    if (capability)
        agentForm.capabilities = [capability];
});
watch(() => jobForm.operation_type, (operationType) => {
    queueReceipt.value = null;
    if (operationType === "deploy") {
        jobForm.resource_scope = "platform";
        jobForm.tenant_id = "";
    }
});
watch(includeRevoked, async () => {
    try {
        await loadAgents();
    }
    catch (error) {
        emit("feedback", { type: "error", message: message(error) });
    }
});
onMounted(loadAll);
; /* PartiallyEnd: #3632/scriptSetup.vue */
function __VLS_template() {
    const __VLS_ctx = {};
    let __VLS_components;
    let __VLS_directives;
    ['operational-panel', 'operational-panel', 'operational-panel', 'operational-panel', 'truth-banner', 'credential', 'credential', 'credential', 'summary', 'summary', 'summary', 'summary', 'summary', 'card', 'card', 'card', 'operational-panel', 'card', 'card', 'card', 'card-title', 'row', 'job-head', 'card-title', 'row', 'row', 'job-head', 'row', 'row', 'job-row', 'primary', 'secondary', 'danger', 'provider-grid', 'provider-grid', 'provider-grid', 'queue-receipt', 'job-row', 'job-meta', 'evidence', 'evidence', 'attention', 'summary', 'operational-grid', 'provider-grid', 'job-form', 'operational-panel', 'card-title', 'row', 'job-head', 'summary', 'provider-grid', 'job-form', 'filters', 'filters',];
    // CSS variable injection 
    // CSS variable injection end 
    __VLS_elementAsFunction(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
        ...{ class: ("operational-panel") },
        'aria-labelledby': ("operational-title"),
    });
    __VLS_elementAsFunction(__VLS_intrinsicElements.header, __VLS_intrinsicElements.header)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({
        ...{ class: ("eyebrow") },
    });
    __VLS_elementAsFunction(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({
        id: ("operational-title"),
    });
    __VLS_elementAsFunction(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
        ...{ onClick: (__VLS_ctx.loadAll) },
        ...{ class: ("secondary") },
        disabled: ((__VLS_ctx.loading)),
    });
    __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
        ...{ class: ("truth-banner") },
    });
    __VLS_elementAsFunction(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
    if (__VLS_ctx.oneTimeCredential) {
        __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: ("credential") },
            role: ("status"),
            'aria-live': ("polite"),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.code, __VLS_intrinsicElements.code)({});
        (__VLS_ctx.oneTimeCredential.header);
        __VLS_elementAsFunction(__VLS_intrinsicElements.code, __VLS_intrinsicElements.code)({
            ...{ class: ("token") },
        });
        (__VLS_ctx.oneTimeCredential.token);
        __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: ("actions") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
            ...{ onClick: (__VLS_ctx.copyCredential) },
            ...{ class: ("primary") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
            ...{ onClick: (...[$event]) => {
                    if (!((__VLS_ctx.oneTimeCredential)))
                        return;
                    __VLS_ctx.oneTimeCredential = null;
                } },
            ...{ class: ("secondary") },
        });
    }
    __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
        ...{ class: ("summary") },
    });
    __VLS_elementAsFunction(__VLS_intrinsicElements.article, __VLS_intrinsicElements.article)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
    (__VLS_ctx.operationalSummary.activeAgents);
    __VLS_elementAsFunction(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
    (__VLS_ctx.operationalSummary.onlineAgents);
    __VLS_elementAsFunction(__VLS_intrinsicElements.article, __VLS_intrinsicElements.article)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
    (__VLS_ctx.operationalSummary.configuredProviders);
    __VLS_elementAsFunction(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.article, __VLS_intrinsicElements.article)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
    (__VLS_ctx.operationalSummary.queuedJobs);
    __VLS_elementAsFunction(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
    (__VLS_ctx.operationalSummary.runningJobs);
    __VLS_elementAsFunction(__VLS_intrinsicElements.article, __VLS_intrinsicElements.article)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
    (__VLS_ctx.operationalSummary.attentionJobs);
    __VLS_elementAsFunction(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
        ...{ class: ("operational-grid") },
    });
    if (__VLS_ctx.canManageAgents) {
        __VLS_elementAsFunction(__VLS_intrinsicElements.form, __VLS_intrinsicElements.form)({
            ...{ onSubmit: (__VLS_ctx.registerAgent) },
            ...{ class: ("card") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.h3, __VLS_intrinsicElements.h3)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.input, __VLS_intrinsicElements.input)({
            pattern: ("[a-z0-9][a-z0-9._-]+"),
            minlength: ("3"),
            required: (true),
            placeholder: ("deploy-host-01"),
        });
        (__VLS_ctx.agentForm.name);
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.select, __VLS_intrinsicElements.select)({
            value: ((__VLS_ctx.agentForm.agent_type)),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
            value: ("host"),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
            value: ("backup"),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
            value: ("restore"),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
            value: ("deploy"),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
            value: ("multi"),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.fieldset, __VLS_intrinsicElements.fieldset)({
            disabled: ((['backup', 'restore', 'deploy'].includes(__VLS_ctx.agentForm.agent_type))),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.legend, __VLS_intrinsicElements.legend)({});
        for (const [option] of __VLS_getVForSourceType((__VLS_ctx.capabilityOptions))) {
            __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({
                key: ((option[0])),
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.input, __VLS_intrinsicElements.input)({
                type: ("checkbox"),
                value: ((option[0])),
            });
            (__VLS_ctx.agentForm.capabilities);
            (option[1]);
        }
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.input, __VLS_intrinsicElements.input)({
            placeholder: ("1.0.0"),
        });
        (__VLS_ctx.agentForm.software_version);
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.input, __VLS_intrinsicElements.input)({
            minlength: ("10"),
            maxlength: ("2000"),
            required: (true),
        });
        (__VLS_ctx.agentForm.reason);
        __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
            ...{ class: ("primary") },
            type: ("submit"),
        });
    }
    __VLS_elementAsFunction(__VLS_intrinsicElements.article, __VLS_intrinsicElements.article)({
        ...{ class: ("card agent-list") },
    });
    __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
        ...{ class: ("card-title") },
    });
    __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.h3, __VLS_intrinsicElements.h3)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({
        ...{ class: ("inline") },
    });
    __VLS_elementAsFunction(__VLS_intrinsicElements.input, __VLS_intrinsicElements.input)({
        type: ("checkbox"),
    });
    (__VLS_ctx.includeRevoked);
    if (__VLS_ctx.canManageAgents) {
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.input, __VLS_intrinsicElements.input)({
            minlength: ("10"),
            placeholder: ("Obrigatório para revogar"),
        });
        (__VLS_ctx.agentRevokeReason);
    }
    if (__VLS_ctx.agents.length) {
        __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: ("rows") },
        });
        for (const [agent] of __VLS_getVForSourceType((__VLS_ctx.agents))) {
            __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                key: ((agent.id)),
                ...{ class: ("row") },
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
            (agent.name);
            __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
            (agent.agent_type);
            (agent.capabilities.join(', '));
            __VLS_elementAsFunction(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
            (__VLS_ctx.connectivityLabel(agent.connectivity));
            (agent.software_version || 'não informada');
            if (__VLS_ctx.canManageAgents && agent.state === 'active') {
                __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                    ...{ onClick: (...[$event]) => {
                            if (!((__VLS_ctx.agents.length)))
                                return;
                            if (!((__VLS_ctx.canManageAgents && agent.state === 'active')))
                                return;
                            __VLS_ctx.revokeAgent(agent);
                        } },
                    ...{ class: ("danger") },
                });
            }
        }
    }
    else {
        __VLS_elementAsFunction(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({
            ...{ class: ("empty") },
        });
    }
    __VLS_elementAsFunction(__VLS_intrinsicElements.article, __VLS_intrinsicElements.article)({
        ...{ class: ("card providers") },
    });
    __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
        ...{ class: ("card-title") },
    });
    __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.h3, __VLS_intrinsicElements.h3)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
    (__VLS_ctx.providers.length);
    __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
        ...{ class: ("provider-grid") },
    });
    for (const [provider] of __VLS_getVForSourceType((__VLS_ctx.providers))) {
        __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            key: ((provider.code)),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
        (provider.code);
        __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
        (provider.category);
        __VLS_elementAsFunction(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({
            ...{ class: ((`provider-${provider.state}`)) },
        });
        (__VLS_ctx.providerState(provider.state));
    }
    __VLS_elementAsFunction(__VLS_intrinsicElements.form, __VLS_intrinsicElements.form)({
        ...{ onSubmit: (__VLS_ctx.queueJob) },
        ...{ class: ("card") },
    });
    __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
        ...{ class: ("card-title") },
    });
    __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.h3, __VLS_intrinsicElements.h3)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
        ...{ class: ("job-form") },
    });
    __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.select, __VLS_intrinsicElements.select)({
        value: ((__VLS_ctx.jobForm.operation_type)),
    });
    __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
        value: ("backup"),
    });
    __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
        value: ("restore"),
    });
    __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
        value: ("deploy"),
    });
    __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.select, __VLS_intrinsicElements.select)({
        value: ((__VLS_ctx.jobForm.resource_scope)),
        disabled: ((__VLS_ctx.jobForm.operation_type === 'deploy')),
    });
    __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
        value: ("platform"),
    });
    __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
        value: ("tenant"),
    });
    if (__VLS_ctx.jobForm.resource_scope === 'tenant' && __VLS_ctx.jobForm.operation_type !== 'deploy') {
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.select, __VLS_intrinsicElements.select)({
            value: ((__VLS_ctx.jobForm.tenant_id)),
            required: (true),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
            value: (""),
        });
        for (const [tenant] of __VLS_getVForSourceType((__VLS_ctx.tenants))) {
            __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
                key: ((tenant.id)),
                value: ((tenant.id)),
            });
            (tenant.trade_name);
            (tenant.code);
        }
    }
    if (__VLS_ctx.jobForm.operation_type === 'restore') {
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.input, __VLS_intrinsicElements.input)({
            pattern: ("[A-Za-z0-9][A-Za-z0-9._:@-]*"),
            required: (true),
            placeholder: ("backup:platform:20260904"),
        });
        (__VLS_ctx.jobForm.backup_reference);
    }
    if (__VLS_ctx.jobForm.operation_type === 'deploy') {
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.select, __VLS_intrinsicElements.select)({
            value: ((__VLS_ctx.jobForm.deployment_target)),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
            value: ("base"),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
            value: ("cloudpanel"),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
            value: ("edge"),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
            value: ("dockge"),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
            value: ("portainer"),
        });
    }
    if (__VLS_ctx.jobForm.operation_type === 'deploy') {
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.select, __VLS_intrinsicElements.select)({
            value: ((__VLS_ctx.jobForm.image_mode)),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
            value: ("registry"),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
            value: ("source"),
        });
    }
    if (__VLS_ctx.jobForm.operation_type === 'deploy') {
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.input, __VLS_intrinsicElements.input)({
            required: (true),
            placeholder: ("1.0.1"),
        });
        (__VLS_ctx.jobForm.release_version);
    }
    __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.input, __VLS_intrinsicElements.input)({
        minlength: ("10"),
        maxlength: ("2000"),
        required: (true),
    });
    (__VLS_ctx.jobForm.reason);
    __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
        ...{ class: ("primary") },
        type: ("submit"),
    });
    if (__VLS_ctx.queueReceipt) {
        __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: ("queue-receipt") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
        (__VLS_ctx.queueReceipt.id);
        __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
        (__VLS_ctx.queueReceipt.execution_started);
        if (!__VLS_ctx.queueReceipt.execution_started) {
            __VLS_elementAsFunction(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
        }
    }
    __VLS_elementAsFunction(__VLS_intrinsicElements.article, __VLS_intrinsicElements.article)({
        ...{ class: ("card jobs") },
    });
    __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
        ...{ class: ("card-title") },
    });
    __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.h3, __VLS_intrinsicElements.h3)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
        ...{ onClick: (__VLS_ctx.loadJobs) },
        ...{ class: ("secondary") },
    });
    __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
        ...{ class: ("filters") },
    });
    __VLS_elementAsFunction(__VLS_intrinsicElements.select, __VLS_intrinsicElements.select)({
        value: ((__VLS_ctx.jobFilters.operation_type)),
    });
    __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
        value: (""),
    });
    __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
        value: ("backup"),
    });
    __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
        value: ("restore"),
    });
    __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
        value: ("deploy"),
    });
    __VLS_elementAsFunction(__VLS_intrinsicElements.select, __VLS_intrinsicElements.select)({
        value: ((__VLS_ctx.jobFilters.state)),
    });
    __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
        value: (""),
    });
    __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
        value: ("queued"),
    });
    __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
        value: ("claimed"),
    });
    __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
        value: ("running"),
    });
    __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
        value: ("succeeded"),
    });
    __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
        value: ("failed"),
    });
    __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
        value: ("cancelled"),
    });
    __VLS_elementAsFunction(__VLS_intrinsicElements.select, __VLS_intrinsicElements.select)({
        value: ((__VLS_ctx.jobFilters.tenant_id)),
    });
    __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
        value: (""),
    });
    for (const [tenant] of __VLS_getVForSourceType((__VLS_ctx.tenants))) {
        __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
            key: ((tenant.id)),
            value: ((tenant.id)),
        });
        (tenant.trade_name);
    }
    __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
        ...{ onClick: (__VLS_ctx.loadJobs) },
        ...{ class: ("secondary") },
    });
    __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.input, __VLS_intrinsicElements.input)({
        minlength: ("10"),
        placeholder: ("Obrigatório para cancelamento"),
    });
    (__VLS_ctx.jobCancelReason);
    if (__VLS_ctx.jobs.length) {
        __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: ("rows") },
        });
        for (const [job] of __VLS_getVForSourceType((__VLS_ctx.jobs))) {
            __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                key: ((job.id)),
                ...{ class: ("job-row") },
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: ("job-head") },
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
            (job.operation_type);
            (__VLS_ctx.tenantName(job.tenant_id));
            __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
            (job.id);
            (job.version);
            __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({
                ...{ class: ((['state', `state-${job.state}`])) },
            });
            (job.state);
            __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: ("job-meta") },
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
            (job.required_capability);
            __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
            (job.assigned_agent_id || 'não atribuído');
            __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
            (job.started_at ? 'sim' : 'não');
            __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
            (job.attempts);
            if (job.attention_required) {
                __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                    ...{ class: ("attention") },
                });
            }
            if (job.result_code || job.failure_code || job.evidence_reference) {
                __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                    ...{ class: ("evidence") },
                });
                if (job.result_code) {
                    __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
                    (job.result_code);
                }
                if (job.failure_code) {
                    __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
                    (job.failure_code);
                }
                if (job.evidence_reference) {
                    __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
                    (job.evidence_reference);
                }
                if (job.evidence_sha256) {
                    __VLS_elementAsFunction(__VLS_intrinsicElements.code, __VLS_intrinsicElements.code)({});
                    (job.evidence_sha256);
                }
            }
            if (job.state === 'queued') {
                __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                    ...{ onClick: (...[$event]) => {
                            if (!((__VLS_ctx.jobs.length)))
                                return;
                            if (!((job.state === 'queued')))
                                return;
                            __VLS_ctx.cancelJob(job);
                        } },
                    ...{ class: ("danger") },
                });
            }
        }
    }
    else {
        __VLS_elementAsFunction(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({
            ...{ class: ("empty") },
        });
    }
    ['operational-panel', 'eyebrow', 'secondary', 'truth-banner', 'credential', 'token', 'actions', 'primary', 'secondary', 'summary', 'operational-grid', 'card', 'primary', 'card', 'agent-list', 'card-title', 'inline', 'rows', 'row', 'danger', 'empty', 'card', 'providers', 'card-title', 'provider-grid', 'card', 'card-title', 'job-form', 'primary', 'queue-receipt', 'card', 'jobs', 'card-title', 'secondary', 'filters', 'secondary', 'rows', 'job-row', 'job-head', 'state', 'job-meta', 'attention', 'evidence', 'danger', 'empty',];
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
            agents: agents,
            providers: providers,
            jobs: jobs,
            includeRevoked: includeRevoked,
            oneTimeCredential: oneTimeCredential,
            queueReceipt: queueReceipt,
            agentRevokeReason: agentRevokeReason,
            jobCancelReason: jobCancelReason,
            canManageAgents: canManageAgents,
            operationalSummary: operationalSummary,
            agentForm: agentForm,
            jobForm: jobForm,
            jobFilters: jobFilters,
            capabilityOptions: capabilityOptions,
            tenantName: tenantName,
            providerState: providerState,
            connectivityLabel: connectivityLabel,
            loadJobs: loadJobs,
            loadAll: loadAll,
            registerAgent: registerAgent,
            copyCredential: copyCredential,
            revokeAgent: revokeAgent,
            queueJob: queueJob,
            cancelJob: cancelJob,
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
