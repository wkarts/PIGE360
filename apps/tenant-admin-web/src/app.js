const { createApp, ref, reactive, computed, onMounted } = Vue;
class ApiFailure extends Error {
    status;
    problem;
    constructor(status, problem) {
        super(problem.detail || problem.title || `Falha HTTP ${status}`);
        this.status = status;
        this.problem = problem;
        this.name = "ApiFailure";
    }
}
class ApiClient {
    refreshPromise = null;
    get accessToken() { return sessionStorage.getItem("tenant.access_token"); }
    get refreshToken() { return sessionStorage.getItem("tenant.refresh_token"); }
    saveTokens(tokens) {
        sessionStorage.setItem("tenant.access_token", tokens.access_token);
        sessionStorage.setItem("tenant.refresh_token", tokens.refresh_token);
        sessionStorage.setItem("tenant.user", JSON.stringify(tokens.user));
    }
    clearTokens() {
        sessionStorage.removeItem("tenant.access_token");
        sessionStorage.removeItem("tenant.refresh_token");
        sessionStorage.removeItem("tenant.user");
    }
    async request(path, options = {}) {
        const method = options.method ?? "GET";
        const url = new URL(path, window.location.origin);
        for (const [key, value] of Object.entries(options.query ?? {})) {
            if (value === undefined || value === null || value === "")
                continue;
            if (Array.isArray(value))
                value.forEach((item) => url.searchParams.append(key, String(item)));
            else
                url.searchParams.set(key, String(value));
        }
        const headers = new Headers({ Accept: "application/json", ...(options.headers ?? {}) });
        if (this.accessToken)
            headers.set("Authorization", `Bearer ${this.accessToken}`);
        if (method !== "GET" && !headers.has("Idempotency-Key") && !path.startsWith("/api/v1/auth/")) {
            headers.set("Idempotency-Key", crypto.randomUUID());
        }
        let body;
        if (options.body !== undefined) {
            headers.set("Content-Type", "application/json");
            body = JSON.stringify(options.body);
        }
        const requestInit = { method, headers, credentials: "same-origin" };
        if (body !== undefined)
            requestInit.body = body;
        const response = await fetch(url, requestInit);
        if (response.status === 401 && options.retryAuthentication !== false && this.refreshToken && !path.endsWith("/auth/refresh")) {
            const refreshed = await this.rotateRefreshToken();
            if (refreshed)
                return this.request(path, { ...options, retryAuthentication: false });
        }
        if (!response.ok) {
            let problem = { status: response.status, title: response.statusText };
            try {
                problem = await response.json();
            }
            catch { /* resposta não estruturada */ }
            throw new ApiFailure(response.status, problem);
        }
        if (options.responseType === "blob")
            return await response.blob();
        if (response.status === 204 || response.headers.get("content-length") === "0")
            return undefined;
        const contentType = response.headers.get("content-type") ?? "";
        if (contentType.includes("json"))
            return await response.json();
        return await response.text();
    }
    async rotateRefreshToken() {
        if (this.refreshPromise)
            return this.refreshPromise;
        this.refreshPromise = (async () => {
            const token = this.refreshToken;
            if (!token)
                return false;
            try {
                const tokens = await this.request("/api/v1/auth/refresh", {
                    method: "POST",
                    body: { refresh_token: token, device_name: navigator.userAgent.slice(0, 180) },
                    retryAuthentication: false,
                });
                this.saveTokens(tokens);
                return true;
            }
            catch {
                this.clearTokens();
                return false;
            }
            finally {
                this.refreshPromise = null;
            }
        })();
        return this.refreshPromise;
    }
}
const fieldLabels = {
    id: "Identificador", code: "Código", name: "Nome", title: "Título", description: "Descrição",
    status: "Status", full_name: "Nome completo", social_name: "Nome social", cpf: "CPF", email: "E-mail",
    phone: "Telefone", birth_date: "Data de nascimento", institution_id: "Instituição", unit_id: "Unidade",
    department_id: "Departamento", position_id: "Cargo", person_id: "Pessoa", employee_id: "Colaborador",
    candidate_id: "Candidato", opening_id: "Vaga", application_id: "Candidatura", employment_type: "Tipo de vínculo",
    workplace_mode: "Modalidade de trabalho", openings_count: "Quantidade de vagas", requirements: "Requisitos",
    responsibilities: "Responsabilidades", salary_floor: "Salário inicial", salary_ceiling: "Salário máximo",
    cbo_code: "CBO", target_start_date: "Data prevista de início", source: "Origem", notes: "Observações",
    action: "Ação", reason: "Motivo", start_date: "Data inicial", end_date: "Data final",
    scheduled_start: "Início programado", scheduled_end: "Fim programado", accrual_start: "Início aquisitivo",
    accrual_end: "Fim aquisitivo", entitlement_days: "Dias de direito", sold_days: "Dias vendidos",
    leave_type: "Tipo de afastamento", paid: "Remunerado", affects_payroll: "Afeta a folha",
    relationship: "Parentesco", tax_dependent: "Dependente para IR", benefit_dependent: "Dependente para benefícios",
    effective_from: "Vigência inicial", salary_amount: "Salário", change_reason: "Motivo da alteração",
    registration_number: "Matrícula", union_id: "Sindicato", base_salary: "Salário-base", admission_date: "Admissão",
    weekly_hours: "Horas semanais", days: "Dias e horários", tolerance_before_minutes: "Tolerância anterior",
    tolerance_after_minutes: "Tolerância posterior", night_start: "Início noturno", night_end: "Fim noturno",
    timezone: "Fuso horário", punched_at: "Data e hora", punch_type: "Tipo de marcação",
    source_idempotency_key: "Chave da origem", device_id: "Dispositivo", location_consent: "Consentimento de localização",
    latitude: "Latitude", longitude: "Longitude", photo_sha256: "Hash da fotografia", metadata: "Metadados",
    program_id: "Programa", curriculum_id: "Currículo", academic_period_id: "Período acadêmico", class_group_id: "Turma",
    student_id: "Aluno", teacher_person_id: "Professor", financial_responsible_person_id: "Responsável financeiro",
    education_level: "Nível de ensino", modality: "Modalidade", workload_hours: "Carga horária", curriculum_version: "Versão curricular",
    period_type: "Tipo de período", starts_on: "Início", ends_on: "Fim", credits: "Créditos", mandatory: "Obrigatório",
    syllabus: "Ementa", shift: "Turno", capacity: "Capacidade", room: "Sala", valid_from: "Válido desde", valid_until: "Válido até",
    primary_teacher: "Professor principal", enrollment_number: "Número da matrícula", enrolled_on: "Data da matrícula",
    accessibility_profile: "Perfil de acessibilidade", target_class_group_id: "Turma de destino", effective_on: "Data efetiva",
    period_start: "Início do período", period_end: "Fim do período", payment_date: "Data de pagamento",
    payroll_type: "Tipo de folha", timekeeping_period_id: "Período de ponto", competence_id: "Competência",
    mode: "Modo", nature: "Natureza", calculation_type: "Forma de cálculo", default_amount: "Valor padrão",
    default_rate: "Percentual padrão", incidences: "Incidências versionadas", formula: "Fórmula parametrizada",
    accounting_debit_code: "Conta de débito", accounting_credit_code: "Conta de crédito", confirmation: "Confirmação", force: "Forçar reprocessamento", publish: "Publicar",
    trade_name: "Nome fantasia", legal_name: "Razão social", document_number: "Documento", contacts: "Contatos",
    sku: "SKU", barcode: "Código de barras", kind: "Tipo", sale_price: "Preço de venda", cost_price: "Custo",
    stock_controlled: "Controla estoque", fiscal_profile: "Perfil fiscal", warehouse_id: "Depósito",
    requester_employee_id: "Solicitante", needed_by: "Necessário até", items: "Itens", supplier_id: "Fornecedor",
    requisition_id: "Requisição", quotation_id: "Cotação", order_number: "Número do pedido", total_amount: "Total",
    tag_number: "Etiqueta patrimonial", acquisition_date: "Data de aquisição", acquisition_value: "Valor de aquisição",
    useful_life_months: "Vida útil em meses", residual_value: "Valor residual", location_id: "Localização",
    parent_id: "Registro superior", cost_center_id: "Centro de custo", created_at: "Criado em", updated_at: "Atualizado em",
    generated_at: "Gerado em", published_at: "Publicado em", employee_count: "Colaboradores", gross_amount: "Proventos",
    deduction_amount: "Descontos", employer_charge_amount: "Encargos", net_amount: "Líquido", competence_code: "Competência",
    sha256: "SHA-256", run_number: "Execução", legal_tables_status: "Tabelas legais",
    provider_type: "Provider", environment: "Ambiente", credential_secret_ref: "Referência segura da credencial",
    certificate_secret_ref: "Referência segura do certificado", enabled: "Habilitado", event_type: "Tipo de evento",
    payload: "Conteúdo do evento", schema_version: "Versão do schema", external_reference: "Referência externa",
    component_id: "Componente curricular", plan_type: "Tipo de planejamento", objectives: "Objetivos",
    curriculum_links: "Alinhamentos curriculares", skills: "Habilidades", competencies: "Competências",
    content: "Conteúdos", methodologies: "Metodologias", resources: "Recursos", assessments: "Avaliações",
    accommodations: "Adaptações e acessibilidade", teaching_plan_id: "Plano de ensino", planned_content: "Conteúdo planejado",
    execution_status: "Situação da execução", executed_content: "Conteúdo ministrado", additional_content: "Conteúdo adicional",
    pending_content: "Conteúdo pendente", expected_teacher_person_id: "Professor previsto", actual_teacher_person_id: "Professor efetivo",
    attendance_policy_id: "Política de frequência", policy_version: "Versão da política", minimum_percentage: "Percentual mínimo",
    rules: "Regras versionadas", attendance_status: "Situação de frequência", presence_minutes: "Minutos de presença",
    late_minutes: "Minutos de atraso", early_departure_minutes: "Minutos de saída antecipada", offline_origin: "Origem offline",
    offline_batch_id: "Lote offline", records: "Registros da chamada", attendance_record_id: "Registro de frequência",
    to_status: "Nova situação", decision: "Decisão", effect_status: "Efeito na frequência", review_notes: "Parecer",
    risk_level: "Nível de risco", percentage: "Percentual", total_sessions: "Sessões consideradas", recorded_count: "Registros",
    contract_number: "Número do contrato", responsible_person_id: "Responsável financeiro", currency: "Moeda",
    recognized_amount: "Valor faturado",
    generation_policy: "Política de geração", terms: "Termos", current_version: "Versão atual",
    plan_number: "Número do plano", installment_count: "Quantidade de parcelas", first_due_date: "Primeiro vencimento",
    interval_months: "Intervalo em meses", discount_amount: "Desconto", billing_rules: "Regras de faturamento",
    charge_number: "Número da cobrança", origin_type: "Tipo de origem",
    origin_id: "Origem", due_date: "Vencimento", accounting_code: "Conta contábil",
    installment_number: "Número da parcela", sequence: "Sequência", amount: "Valor", paid_amount: "Valor pago",
    refunded_amount: "Valor reembolsado", outstanding_amount: "Saldo", penalty_amount: "Multa",
    interest_amount: "Juros", payment_number: "Número do pagamento", payer_person_id: "Pagador", direction: "Direção",
    method: "Forma de pagamento", allocations: "Alocações", confirm: "Confirmar imediatamente",
    refund_number: "Número do reembolso", payment_allocation_id: "Alocação do pagamento", payable_number: "Número da conta",
    scholarship_type: "Tipo de bolsa", fixed_amount: "Valor fixo",
    penalty_type: "Tipo de encargo", rule_snapshot: "Snapshot da regra",
    batch_number: "Número do lote", reference_type: "Tipo de referência", reference_id: "Referência",
    total_debit: "Total de débitos", total_credit: "Total de créditos", occurred_at: "Ocorrido em",
    catalog_id: "Catálogo", service_id: "Serviço", variant_id: "Variação", service_type: "Tipo de serviço",
    recurrence_type: "Recorrência", unit_of_measure: "Unidade de medida", default_duration_minutes: "Duração padrão",
    taxable: "Tributável", nbs_code: "NBS", lc116_code: "Item LC 116", municipal_service_code: "Código municipal",
    cnae_code: "CNAE", iss_rate: "Alíquota ISS", ibs_rate: "Alíquota IBS", cbs_rate: "Alíquota CBS",
    cclass_trib: "cClassTrib", fiscal_trigger: "Gatilho fiscal", withholding: "Retenções", rules_snapshot: "Snapshot fiscal",
    billing_frequency: "Periodicidade", billing_trigger: "Gatilho de cobrança",
    due_day: "Dia de vencimento", recognition_policy: "Reconhecimento", proration_policy: "Rateio proporcional",
    subscription_number: "Número da assinatura", subscriber_person_id: "Assinante", billing_rule_id: "Regra de cobrança",
    quantity: "Quantidade", unit_price: "Preço unitário", auto_renew: "Renovação automática",
    next_competence_on: "Próxima competência", order_id: "Pedido", order_item_id: "Item do pedido", execution_number: "Execução",
    scheduled_at: "Agendada em", performer_person_id: "Executor", completed_quantity: "Quantidade concluída",
    fiscal_status: "Situação fiscal", requested_at: "Solicitado em", provider_status: "Situação do provider"
};
const statusLabels = {
    active: "Ativo", inactive: "Inativo", draft: "Rascunho", published: "Publicado", paused: "Pausado",
    closed: "Fechado", reopened: "Reaberto", cancelled: "Cancelado", completed: "Concluído", pending: "Pendente",
    submitted: "Enviado", approved: "Aprovado", rejected: "Rejeitado", in_progress: "Em andamento",
    scheduled: "Programado", on_leave: "Afastado", vacation: "Em férias", terminated: "Desligado",
    open: "Aberto", processing: "Processando", processed: "Processado", generated: "Gerado", paid: "Pago",
    partially_received: "Recebido parcialmente", received: "Recebido", partially_approved: "Aprovado parcialmente",
    not_configured: "Não configurado", configured: "Configurado", healthy: "Saudável", failed: "Falhou",
    simulation: "Simulação", production: "Produção", regular: "Regular", earning: "Provento", deduction: "Desconto",
    employer_charge: "Encargo patronal", informational: "Informativo", fixed: "Valor fixo", percentage: "Percentual",
    hourly: "Por hora", web: "Web", mobile: "Mobile", desktop: "Desktop", kiosk: "Terminal", rep: "REP",
    afd: "AFD", offline: "Offline", api: "API", entry: "Entrada", exit: "Saída", break_start: "Início do intervalo",
    break_end: "Fim do intervalo", adjustment: "Ajuste", clt: "CLT", temporary: "Temporário", internship: "Estágio",
    apprentice: "Aprendiz", contractor: "Prestador", public_servant: "Servidor público", onsite: "Presencial",
    hybrid: "Híbrido", remote: "Remoto", publish: "Publicar", pause: "Pausar", reopen: "Reabrir", close: "Fechar",
    schedule: "Programar", approve: "Aprovar", start: "Iniciar", complete: "Concluir", cancel: "Cancelar",
    submitted_for_review: "Enviado para revisão", changes_requested: "Alterações solicitadas", partially_executed: "Executado parcialmente",
    executed: "Executado", not_executed: "Não executado", rescheduled: "Reagendado", attendance_open: "Chamada aberta",
    attendance_submitted: "Chamada enviada", present: "Presente", absent: "Ausente", justified_absence: "Falta justificada",
    excused_absence: "Falta abonada", late: "Atraso", late_justified: "Atraso justificado", early_departure: "Saída antecipada",
    remote_present: "Presença remota", activity_present: "Presença em atividade", critical: "Crítico", high: "Alto",
    watch: "Atenção", none: "Sem risco", superseded: "Substituído", archived: "Arquivado",
    partially_paid: "Pago parcialmente", confirmed: "Confirmado", partially_refunded: "Reembolsado parcialmente",
    refunded: "Reembolsado", incoming: "Entrada", outgoing: "Saída", blocked_validation: "Bloqueado por validação",
    one_time: "Avulso", monthly: "Mensal", bimonthly: "Bimestral",
    quarterly: "Trimestral", semiannual: "Semestral", annual: "Anual", competence: "Competência", billing: "Faturamento",
    payment: "Pagamento", execution: "Execução", manual: "Manual", full_cycle: "Ciclo integral", daily: "Diário",
    monthly_30: "Mensal (30 dias)"
};
const col = (key, label, format) => {
    const column = { key, label: label ?? fieldLabels[key] ?? key };
    if (format !== undefined)
        column.format = format;
    return column;
};
const resources = [
    { id: "people", group: "Cadastros", icon: "◎", title: "Pessoas", description: "Cadastro único de pessoas e contatos institucionais.", listPath: "/api/v1/people", createPath: "/api/v1/people", detailPath: (row) => `/api/v1/people/${row.id}`, columns: [col("full_name"), col("cpf"), col("email"), col("phone"), col("status")], searchParam: "search", statusParam: "status" },
    { id: "students", group: "Secretaria acadêmica", icon: "♟", title: "Alunos", description: "Cadastro acadêmico do aluno vinculado à pessoa única, responsáveis e acessibilidade.", listPath: "/api/v1/students", createPath: "/api/v1/students", detailPath: (row) => `/api/v1/students/${row.id}`, columns: [col("registration_number"), col("person.full_name", "Nome"), col("person.cpf", "CPF"), col("admission_date", undefined, "date"), col("status")], searchParam: "search", statusParam: "status" },
    { id: "academic-programs", group: "Secretaria acadêmica", icon: "▰", title: "Programas", description: "Programas educacionais por nível, modalidade e carga horária.", listPath: "/api/v1/academic/programs", createPath: "/api/v1/academic/programs", columns: [col("code"), col("name"), col("education_level"), col("modality"), col("status")], searchParam: "search", statusParam: "status" },
    { id: "curricula", group: "Secretaria acadêmica", icon: "▱", title: "Currículos", description: "Currículos versionados com vigência e vínculo ao programa.", listPath: "/api/v1/academic/curricula", createPath: "/api/v1/academic/curricula", columns: [col("code"), col("name"), col("curriculum_version"), col("valid_from", undefined, "date"), col("status")], statusParam: "status" },
    { id: "academic-periods", group: "Secretaria acadêmica", icon: "▣", title: "Períodos acadêmicos", description: "Anos, semestres, módulos e demais períodos com fechamento controlado.", listPath: "/api/v1/academic/periods", createPath: "/api/v1/academic/periods", columns: [col("code"), col("name"), col("year"), col("starts_on", undefined, "date"), col("status")], statusParam: "status", actions: [{ label: "Alterar estado", method: "POST", path: (row) => `/api/v1/academic/periods/${row.id}/transition`, openApiPath: "/api/v1/academic/periods/{period_id}/transition", schemaName: "PeriodTransition" }] },
    { id: "academic-components", group: "Secretaria acadêmica", icon: "◈", title: "Componentes curriculares", description: "Disciplinas e componentes vinculados ao currículo, carga horária e ementa.", listPath: "/api/v1/academic/components", createPath: "/api/v1/academic/components", columns: [col("code"), col("name"), col("workload_hours", undefined, "number"), col("credits", undefined, "number"), col("status")], searchParam: "search" },
    { id: "class-groups", group: "Secretaria acadêmica", icon: "▤", title: "Turmas", description: "Turmas, capacidade, turno, sala e ocupação por período.", listPath: "/api/v1/academic/classes", createPath: "/api/v1/academic/classes", columns: [col("code"), col("name"), col("shift"), col("capacity", undefined, "number"), col("active_enrollment_count", "Ocupação", "number"), col("status")], searchParam: "search", statusParam: "status" },
    { id: "teacher-assignments", group: "Secretaria acadêmica", icon: "♙", title: "Atribuições docentes", description: "Vínculo versionado entre professor, turma e componente curricular.", listPath: "/api/v1/academic/teacher-assignments", createPath: "/api/v1/academic/teacher-assignments", columns: [col("teacher_person_id"), col("class_group_id"), col("component_id"), col("valid_from", undefined, "date"), col("status")] },
    { id: "enrollments", group: "Secretaria acadêmica", icon: "✓", title: "Matrículas", description: "Matrícula, ativação, movimentações, capacidade e mudança de turma auditada.", listPath: "/api/v1/enrollments", createPath: "/api/v1/enrollments", detailPath: (row) => `/api/v1/enrollments/${row.id}`, columns: [col("enrollment_number"), col("student_id"), col("class_group_id"), col("enrolled_on", undefined, "date"), col("status")], searchParam: "search", statusParam: "status", actions: [
            { label: "Alterar estado", method: "POST", path: (row) => `/api/v1/enrollments/${row.id}/transition`, openApiPath: "/api/v1/enrollments/{enrollment_id}/transition", schemaName: "EnrollmentTransition" },
            { label: "Mudar turma", method: "POST", path: (row) => `/api/v1/enrollments/${row.id}/transfer`, openApiPath: "/api/v1/enrollments/{enrollment_id}/transfer", schemaName: "EnrollmentTransfer", visible: (row) => ["active", "suspended", "locked"].includes(row.status) }
        ] },
    { id: "teaching-plans", group: "Pedagógico", icon: "▧", title: "Planos de ensino", description: "Planejamento versionado, alinhamento curricular, revisão, aprovação e reaproveitamento.", listPath: "/api/v1/teaching-plans", createPath: "/api/v1/teaching-plans", detailPath: (row) => `/api/v1/teaching-plans/${row.id}`, columns: [col("title"), col("teacher_person_id"), col("starts_on", undefined, "date"), col("current_version", "Versão", "number"), col("status")], searchParam: "search", statusParam: "status", actions: [
            { label: "Enviar para revisão", method: "POST", direct: true, path: (row) => `/api/v1/teaching-plans/${row.id}/submit`, openApiPath: "/api/v1/teaching-plans/{plan_id}/submit", visible: (row) => ["draft", "changes_requested"].includes(row.status) },
            { label: "Nova versão", method: "POST", path: (row) => `/api/v1/teaching-plans/${row.id}/versions`, openApiPath: "/api/v1/teaching-plans/{plan_id}/versions", schemaName: "TeachingPlanVersionCreate", visible: (row) => !["archived", "superseded"].includes(row.status) },
            { label: "Aprovar", method: "POST", path: (row) => `/api/v1/teaching-plans/${row.id}/approve`, openApiPath: "/api/v1/teaching-plans/{plan_id}/approve", schemaName: "ReviewDecision", visible: (row) => row.status === "submitted_for_review" },
            { label: "Solicitar alterações", method: "POST", path: (row) => `/api/v1/teaching-plans/${row.id}/request-changes`, openApiPath: "/api/v1/teaching-plans/{plan_id}/request-changes", schemaName: "RequestChanges", visible: (row) => row.status === "submitted_for_review" },
            { label: "Duplicar", method: "POST", path: (row) => `/api/v1/teaching-plans/${row.id}/duplicate`, openApiPath: "/api/v1/teaching-plans/{plan_id}/duplicate", schemaName: "TeachingPlanDuplicate" },
            { label: "Arquivar", method: "POST", direct: true, path: (row) => `/api/v1/teaching-plans/${row.id}/archive`, openApiPath: "/api/v1/teaching-plans/{plan_id}/archive", visible: (row) => row.status !== "archived" }
        ] },
    { id: "lesson-plans", group: "Pedagógico", icon: "▥", title: "Planos de aula", description: "Agenda da aula, execução planejada versus ministrada, reposição e cancelamento.", listPath: "/api/v1/lesson-plans", createPath: "/api/v1/lesson-plans", detailPath: (row) => `/api/v1/lesson-plans/${row.id}`, columns: [col("title"), col("teacher_person_id"), col("scheduled_start", undefined, "datetime"), col("scheduled_end", undefined, "datetime"), col("status")], statusParam: "status", actions: [
            { label: "Iniciar aula", method: "POST", direct: true, path: (row) => `/api/v1/lesson-plans/${row.id}/start`, openApiPath: "/api/v1/lesson-plans/{lesson_id}/start", visible: (row) => ["scheduled", "ready"].includes(row.status) },
            { label: "Registrar execução", method: "POST", path: (row) => `/api/v1/lesson-plans/${row.id}/complete`, openApiPath: "/api/v1/lesson-plans/{lesson_id}/complete", schemaName: "LessonExecution", visible: (row) => row.status === "in_progress" },
            { label: "Reagendar", method: "POST", path: (row) => `/api/v1/lesson-plans/${row.id}/reschedule`, openApiPath: "/api/v1/lesson-plans/{lesson_id}/reschedule", schemaName: "LessonReschedule", visible: (row) => ["scheduled", "ready", "partially_executed", "not_executed"].includes(row.status) },
            { label: "Cancelar", method: "POST", path: (row) => `/api/v1/lesson-plans/${row.id}/cancel`, openApiPath: "/api/v1/lesson-plans/{lesson_id}/cancel", schemaName: "LessonCancel", visible: (row) => ["scheduled", "ready"].includes(row.status) }
        ] },
    { id: "attendance-policies", group: "Frequência escolar", icon: "⚙", title: "Políticas de frequência", description: "Percentuais, tolerâncias e pesos versionados por vigência.", listPath: "/api/v1/attendance/policies", createPath: "/api/v1/attendance/policies", columns: [col("code"), col("name"), col("policy_version", undefined, "number"), col("minimum_percentage", undefined, "number"), col("status")], statusParam: "status" },
    { id: "class-sessions", group: "Frequência escolar", icon: "✓", title: "Sessões e chamada", description: "Sessão real, chamada online/offline, envio, fechamento, reabertura e correções auditadas.", listPath: "/api/v1/class-sessions", createPath: "/api/v1/class-sessions", detailPath: (row) => `/api/v1/class-sessions/${row.id}`, columns: [col("class_group_id"), col("component_id"), col("scheduled_start", undefined, "datetime"), col("actual_teacher_person_id"), col("status")], statusParam: "status", actions: [
            { label: "Iniciar sessão", method: "POST", path: (row) => `/api/v1/class-sessions/${row.id}/start`, openApiPath: "/api/v1/class-sessions/{session_id}/start", schemaName: "SessionStart", visible: (row) => ["scheduled", "ready", "reopened"].includes(row.status) },
            { label: "Registrar chamada", method: "PUT", path: (row) => `/api/v1/class-sessions/${row.id}/attendance`, openApiPath: "/api/v1/class-sessions/{session_id}/attendance", schemaName: "AttendanceUpsert", visible: (row) => ["attendance_open", "started", "reopened"].includes(row.status) },
            { label: "Enviar chamada", method: "POST", direct: true, path: (row) => `/api/v1/class-sessions/${row.id}/attendance/submit`, openApiPath: "/api/v1/class-sessions/{session_id}/attendance/submit", visible: (row) => ["attendance_open", "reopened"].includes(row.status) },
            { label: "Fechar sessão", method: "POST", direct: true, path: (row) => `/api/v1/class-sessions/${row.id}/close`, openApiPath: "/api/v1/class-sessions/{session_id}/close", visible: (row) => row.status === "attendance_submitted" },
            { label: "Reabrir", method: "POST", path: (row) => `/api/v1/class-sessions/${row.id}/reopen`, openApiPath: "/api/v1/class-sessions/{session_id}/reopen", schemaName: "SessionReopen", visible: (row) => row.status === "closed" },
            { label: "Reagendar", method: "POST", path: (row) => `/api/v1/class-sessions/${row.id}/reschedule`, openApiPath: "/api/v1/class-sessions/{session_id}/reschedule", schemaName: "SessionReschedule", visible: (row) => ["scheduled", "ready", "cancelled"].includes(row.status) },
            { label: "Cancelar", method: "POST", path: (row) => `/api/v1/class-sessions/${row.id}/cancel`, openApiPath: "/api/v1/class-sessions/{session_id}/cancel", schemaName: "SessionCancel", visible: (row) => ["scheduled", "ready"].includes(row.status) }
        ] },
    { id: "attendance-justifications", group: "Frequência escolar", icon: "✎", title: "Justificativas", description: "Solicitações, análise e efeito parametrizado sobre o registro de frequência.", listPath: "/api/v1/attendance/justifications", createPath: "/api/v1/attendance/justifications", columns: [col("student_id"), col("attendance_record_id"), col("reason"), col("created_at", undefined, "datetime"), col("status")], statusParam: "status", actions: [
            { label: "Analisar", method: "POST", path: (row) => `/api/v1/attendance/justifications/${row.id}/review`, openApiPath: "/api/v1/attendance/justifications/{justification_id}/review", schemaName: "AttendanceJustificationReview", visible: (row) => ["submitted", "under_review", "additional_information_required"].includes(row.status) }
        ] },
    { id: "attendance-risks", group: "Frequência escolar", icon: "!", title: "Risco de frequência", description: "Indicadores por aluno, período e componente vinculados à versão da política.", listPath: "/api/v1/attendance/risks", columns: [col("student_id"), col("academic_period_id"), col("component_id"), col("total_sessions", undefined, "number"), col("percentage", undefined, "number"), col("risk_level")] },
    { id: "departments", group: "Recursos humanos", icon: "▦", title: "Departamentos", description: "Estrutura organizacional, hierarquia e centros de custo.", listPath: "/api/v1/hr/departments", createPath: "/api/v1/hr/departments", columns: [col("code"), col("name"), col("parent_id"), col("status")], searchParam: "search", statusParam: "status" },
    { id: "positions", group: "Recursos humanos", icon: "◇", title: "Cargos e funções", description: "Cargos, CBO, faixas salariais, responsabilidades e requisitos.", listPath: "/api/v1/hr/positions", createPath: "/api/v1/hr/positions", columns: [col("code"), col("title"), col("cbo_code"), col("salary_floor", undefined, "money"), col("status")], searchParam: "search", statusParam: "status" },
    { id: "job-openings", group: "Recursos humanos", icon: "⌕", title: "Vagas", description: "Recrutamento com publicação, pausa, reabertura e encerramento auditados.", listPath: "/api/v1/hr/job-openings", createPath: "/api/v1/hr/job-openings", detailPath: (row) => `/api/v1/hr/job-openings/${row.id}`, columns: [col("position_id"), col("employment_type"), col("openings_count"), col("target_start_date", undefined, "date"), col("status")], statusParam: "status", actions: [{ label: "Alterar estado", method: "POST", path: (row) => `/api/v1/hr/job-openings/${row.id}/transition`, openApiPath: "/api/v1/hr/job-openings/{opening_id}/transition", schemaName: "JobOpeningTransition" }] },
    { id: "candidates", group: "Recursos humanos", icon: "◉", title: "Candidatos", description: "Banco de candidatos vinculado ao cadastro único de pessoas.", listPath: "/api/v1/hr/candidates", createPath: "/api/v1/hr/candidates", columns: [col("person_id"), col("source"), col("linkedin_url"), col("status")], statusParam: "status" },
    { id: "applications", group: "Recursos humanos", icon: "⇢", title: "Candidaturas", description: "Candidaturas e etapas do processo seletivo.", listPath: "/api/v1/hr/applications", createPath: "/api/v1/hr/applications", detailPath: (row) => `/api/v1/hr/applications/${row.id}`, columns: [col("candidate_id"), col("job_opening_id", "Vaga"), col("current_stage"), col("score", "Pontuação", "number"), col("status")] },
    { id: "admissions", group: "Recursos humanos", icon: "✓", title: "Admissões", description: "Checklist admissional, aprovação e contratação transacional.", listPath: "/api/v1/hr/admissions", createPath: "/api/v1/hr/admissions", detailPath: (row) => `/api/v1/hr/admissions/${row.id}`, columns: [col("candidate_id"), col("position_id"), col("planned_start_date", "Início previsto", "date"), col("status")], statusParam: "status" },
    { id: "employees", group: "Recursos humanos", icon: "♙", title: "Colaboradores", description: "Colaboradores, contratos, lotações e histórico funcional.", listPath: "/api/v1/hr/employees", detailPath: (row) => `/api/v1/hr/employees/${row.id}`, columns: [col("registration_number"), col("person_id"), col("admission_date", undefined, "date"), col("employment_status", "Situação")], searchParam: "search", statusParam: "status" },
    { id: "vacations", group: "Recursos humanos", icon: "☼", title: "Férias", description: "Períodos aquisitivos, programação, aprovação, início e conclusão.", listPath: "/api/v1/hr/vacations", createPath: "/api/v1/hr/vacations", columns: [col("employee_id"), col("accrual_start", undefined, "date"), col("accrual_end", undefined, "date"), col("scheduled_start", undefined, "date"), col("status")], statusParam: "status", actions: [{ label: "Alterar estado", method: "POST", path: (row) => `/api/v1/hr/vacations/${row.id}/transition`, openApiPath: "/api/v1/hr/vacations/{vacation_id}/transition", schemaName: "VacationTransition" }] },
    { id: "leaves", group: "Recursos humanos", icon: "✚", title: "Afastamentos", description: "Afastamentos remunerados ou não e seus efeitos na folha.", listPath: "/api/v1/hr/leaves", createPath: "/api/v1/hr/leaves", columns: [col("employee_id"), col("leave_type"), col("start_date", undefined, "date"), col("end_date", undefined, "date"), col("status")], statusParam: "status", actions: [{ label: "Decidir", method: "POST", path: (row) => `/api/v1/hr/leaves/${row.id}/transition`, openApiPath: "/api/v1/hr/leaves/{leave_id}/transition", schemaName: "LeaveTransition" }] },
    { id: "training", group: "Desenvolvimento", icon: "△", title: "Treinamentos", description: "Cursos internos, inscrições, conclusão e certificados.", listPath: "/api/v1/hr/training-courses", createPath: "/api/v1/hr/training-courses", columns: [col("code"), col("name"), col("provider_name", "Fornecedor"), col("workload_hours", "Carga horária", "number"), col("status")], searchParam: "search", statusParam: "status" },
    { id: "performance", group: "Desenvolvimento", icon: "☆", title: "Avaliações", description: "Avaliações de desempenho e acompanhamento de resultados.", listPath: "/api/v1/hr/performance-reviews", createPath: "/api/v1/hr/performance-reviews", columns: [col("employee_id"), col("review_period_start", "Período inicial", "date"), col("review_period_end", "Período final", "date"), col("overall_score", "Nota", "number"), col("status")], statusParam: "status" },
    { id: "dependents", group: "Setor pessoal", icon: "♧", title: "Dependentes", description: "Dependentes trabalhistas, fiscais e de benefícios.", listPath: "/api/v1/personnel/dependents", createPath: "/api/v1/personnel/dependents", columns: [col("employee_id"), col("person_id"), col("relationship"), col("tax_dependent", undefined, "boolean"), col("status")], statusParam: "status" },
    { id: "salary-history", group: "Setor pessoal", icon: "↗", title: "Histórico salarial", description: "Alterações salariais com vigência e motivo auditável.", listPath: "/api/v1/personnel/salary-history", createPath: "/api/v1/personnel/salary-history", columns: [col("employee_id"), col("effective_from", undefined, "date"), col("salary_amount", undefined, "money"), col("change_reason")] },
    { id: "unions", group: "Setor pessoal", icon: "⌂", title: "Sindicatos", description: "Sindicatos, bases territoriais e referências de instrumentos coletivos.", listPath: "/api/v1/personnel/unions", createPath: "/api/v1/personnel/unions", columns: [col("code"), col("name"), col("document_number"), col("status")], statusParam: "status" },
    { id: "loans", group: "Setor pessoal", icon: "¤", title: "Empréstimos", description: "Empréstimos e parcelas consignadas integradas à folha.", listPath: "/api/v1/personnel/loans", createPath: "/api/v1/personnel/loans", columns: [col("employee_id"), col("principal_amount", "Principal", "money"), col("installment_amount", "Parcela", "money"), col("paid_installments", "Pagas", "number"), col("status")], statusParam: "status" },
    { id: "terminations", group: "Setor pessoal", icon: "⊘", title: "Desligamentos", description: "Processo de desligamento e transições de aprovação.", listPath: "/api/v1/personnel/terminations", createPath: "/api/v1/personnel/terminations", detailPath: (row) => `/api/v1/personnel/terminations/${row.id}`, columns: [col("employee_id"), col("termination_date", "Data", "date"), col("termination_type", "Tipo"), col("status")], statusParam: "status" },
    { id: "government-providers", group: "Setor pessoal", icon: "▣", title: "Obrigações legais", description: "Providers versionados; transmissões reais permanecem desativadas sem configuração homologada.", listPath: "/api/v1/personnel/government/providers", createPath: "/api/v1/personnel/government/providers", columns: [col("provider_type"), col("environment"), col("enabled", undefined, "boolean"), col("status")], statusParam: "status" },
    { id: "shifts", group: "Controle de ponto", icon: "◷", title: "Turnos", description: "Turnos, tolerâncias, intervalos e adicional noturno.", listPath: "/api/v1/timekeeping/shifts", createPath: "/api/v1/timekeeping/shifts", columns: [col("code"), col("name"), col("start_time", "Entrada"), col("end_time", "Saída"), col("status")], statusParam: "status" },
    { id: "schedules", group: "Controle de ponto", icon: "▤", title: "Jornadas", description: "Jornadas semanais e dias vinculados a turnos.", listPath: "/api/v1/timekeeping/schedules", createPath: "/api/v1/timekeeping/schedules", detailPath: (row) => `/api/v1/timekeeping/schedules/${row.id}`, columns: [col("code"), col("name"), col("weekly_hours", undefined, "number"), col("status")], statusParam: "status" },
    { id: "devices", group: "Controle de ponto", icon: "▥", title: "Dispositivos", description: "Terminais, REP e dispositivos de marcação.", listPath: "/api/v1/timekeeping/devices", createPath: "/api/v1/timekeeping/devices", columns: [col("code"), col("name"), col("device_type", "Tipo"), col("serial_number", "Número de série"), col("status")], statusParam: "status" },
    { id: "punches", group: "Controle de ponto", icon: "●", title: "Marcações", description: "Marcações online, mobile, terminais, REP, AFD e offline.", listPath: "/api/v1/timekeeping/punches", createPath: "/api/v1/timekeeping/punches", columns: [col("employee_id"), col("punched_at", undefined, "datetime"), col("punch_type"), col("source"), col("integrity_sha256", "Integridade")] },
    { id: "timekeeping-periods", group: "Controle de ponto", icon: "▧", title: "Períodos e espelhos", description: "Apuração, aprovação, fechamento e reabertura do ponto.", listPath: "/api/v1/timekeeping/periods", createPath: "/api/v1/timekeeping/periods", detailPath: (row) => `/api/v1/timekeeping/periods/${row.id}`, columns: [col("code"), col("start_date", undefined, "date"), col("end_date", undefined, "date"), col("status")], statusParam: "status", actions: [
            { label: "Calcular", method: "POST", direct: true, path: (row) => `/api/v1/timekeeping/periods/${row.id}/calculate`, openApiPath: "/api/v1/timekeeping/periods/{period_id}/calculate", visible: (row) => ["open", "reopened", "calculated"].includes(row.status) },
            { label: "Fechar", method: "POST", direct: true, path: (row) => `/api/v1/timekeeping/periods/${row.id}/close`, openApiPath: "/api/v1/timekeeping/periods/{period_id}/close", visible: (row) => row.status !== "closed" },
            { label: "Reabrir", method: "POST", path: (row) => `/api/v1/timekeeping/periods/${row.id}/reopen`, openApiPath: "/api/v1/timekeeping/periods/{period_id}/reopen", schemaName: "PeriodReopen", visible: (row) => row.status === "closed" }
        ] },
    { id: "payroll-rubrics", group: "Folha de pagamento", icon: "≡", title: "Rubricas", description: "Rubricas, incidências, fórmulas e contas contábeis versionadas.", listPath: "/api/v1/payroll/rubrics", createPath: "/api/v1/payroll/rubrics", columns: [col("code"), col("name"), col("nature"), col("calculation_type"), col("status")], statusParam: "status" },
    { id: "payroll-competences", group: "Folha de pagamento", icon: "▨", title: "Competências", description: "Competências regulares, férias, décimo terceiro, rescisão e suplementar.", listPath: "/api/v1/payroll/competences", createPath: "/api/v1/payroll/competences", detailPath: (row) => `/api/v1/payroll/competences/${row.id}`, columns: [col("code"), col("payroll_type"), col("payment_date", undefined, "date"), col("status")], statusParam: "status", actions: [
            { label: "Fechar", method: "POST", direct: true, path: (row) => `/api/v1/payroll/competences/${row.id}/close`, openApiPath: "/api/v1/payroll/competences/{competence_id}/close", visible: (row) => row.status !== "closed" },
            { label: "Reabrir", method: "POST", path: (row) => `/api/v1/payroll/competences/${row.id}/reopen`, openApiPath: "/api/v1/payroll/competences/{competence_id}/reopen", schemaName: "PayrollCompetenceReopen", visible: (row) => row.status === "closed" }
        ] },
    { id: "payroll-runs", group: "Folha de pagamento", icon: "▶", title: "Processamentos", description: "Simulações e processamentos de produção idempotentes.", listPath: "/api/v1/payroll/runs", createPath: "/api/v1/payroll/runs", detailPath: (row) => `/api/v1/payroll/runs/${row.id}`, columns: [col("run_number"), col("mode"), col("employee_count", undefined, "number"), col("net_amount", undefined, "money"), col("status")], statusParam: "status", actions: [
            { label: "Processar", method: "POST", path: (row) => `/api/v1/payroll/runs/${row.id}/process`, openApiPath: "/api/v1/payroll/runs/{run_id}/process", schemaName: "PayrollRunProcess", visible: (row) => ["draft", "failed"].includes(row.status) },
            { label: "Holerites", method: "POST", direct: true, path: (row) => `/api/v1/payroll/runs/${row.id}/payslips`, openApiPath: "/api/v1/payroll/runs/{run_id}/payslips", visible: (row) => row.status === "processed" && row.mode === "production" },
            { label: "Contabilizar", method: "POST", direct: true, path: (row) => `/api/v1/payroll/runs/${row.id}/accounting`, openApiPath: "/api/v1/payroll/runs/{run_id}/accounting", visible: (row) => row.status === "processed" },
            { label: "Fechar", method: "POST", path: (row) => `/api/v1/payroll/runs/${row.id}/close`, openApiPath: "/api/v1/payroll/runs/{run_id}/close", schemaName: "PayrollRunClose", visible: (row) => row.status === "processed" }
        ] },
    { id: "payslips", group: "Folha de pagamento", icon: "▱", title: "Holerites", description: "Holerites físicos com SHA-256, publicação e download autorizado.", listPath: "/api/v1/payroll/payslips", detailPath: (row) => `/api/v1/payroll/payslips/${row.id}`, columns: [col("document_number"), col("employee_id"), col("competence_code"), col("generated_at", undefined, "datetime"), col("status")], statusParam: "status", actions: [
            { label: "Publicar", method: "POST", path: (row) => `/api/v1/payroll/payslips/${row.id}/publish`, openApiPath: "/api/v1/payroll/payslips/{payslip_id}/publish", schemaName: "PayslipPublish", visible: (row) => row.status !== "published" },
            { label: "Baixar", method: "GET", direct: true, download: true, path: (row) => `/api/v1/payroll/payslips/${row.id}/download`, openApiPath: "/api/v1/payroll/payslips/{payslip_id}/download" }
        ] },
    { id: "warehouses", group: "Estoque e compras", icon: "▰", title: "Depósitos", description: "Depósitos e saldos isolados por instituição e unidade.", listPath: "/api/v1/warehouses", createPath: "/api/v1/warehouses", detailPath: (row) => `/api/v1/warehouses/${row.id}`, columns: [col("code"), col("name"), col("status")], searchParam: "search", statusParam: "status" },
    { id: "products", group: "Estoque e compras", icon: "□", title: "Produtos", description: "Produtos, preços, código de barras, estoque e perfil fiscal.", listPath: "/api/v1/products", createPath: "/api/v1/products", detailPath: (row) => `/api/v1/products/${row.id}`, columns: [col("sku"), col("name"), col("sale_price", undefined, "money"), col("cost_price", undefined, "money"), col("status")], searchParam: "search", statusParam: "status" },
    { id: "inventory-balances", group: "Estoque e compras", icon: "▥", title: "Saldos de estoque", description: "Saldo e custo médio por produto e depósito.", listPath: "/api/v1/inventory/balances", columns: [col("product_id"), col("warehouse_id"), col("quantity", "Quantidade", "number"), col("reserved_quantity", "Reservado", "number"), col("average_cost", "Custo médio", "money")] },
    { id: "suppliers", group: "Estoque e compras", icon: "♢", title: "Fornecedores", description: "Fornecedores, contatos e dados comerciais.", listPath: "/api/v1/suppliers", createPath: "/api/v1/suppliers", detailPath: (row) => `/api/v1/suppliers/${row.id}`, columns: [col("code"), col("legal_name"), col("trade_name"), col("document_number"), col("status")], searchParam: "search", statusParam: "status" },
    { id: "requisitions", group: "Estoque e compras", icon: "↟", title: "Requisições de compra", description: "Solicitação, submissão, aprovação, rejeição e cancelamento.", listPath: "/api/v1/procurement/requisitions", createPath: "/api/v1/procurement/requisitions", detailPath: (row) => `/api/v1/procurement/requisitions/${row.id}`, columns: [col("request_number", "Número"), col("requester_employee_id"), col("needed_by", undefined, "date"), col("status")], statusParam: "status", actions: [
            { label: "Enviar", method: "POST", direct: true, path: (row) => `/api/v1/procurement/requisitions/${row.id}/submit`, openApiPath: "/api/v1/procurement/requisitions/{requisition_id}/submit", visible: (row) => row.status === "draft" },
            { label: "Aprovar", method: "POST", path: (row) => `/api/v1/procurement/requisitions/${row.id}/approve`, openApiPath: "/api/v1/procurement/requisitions/{requisition_id}/approve", schemaName: "RequisitionApproval", visible: (row) => row.status === "submitted" },
            { label: "Rejeitar", method: "POST", path: (row) => `/api/v1/procurement/requisitions/${row.id}/reject`, openApiPath: "/api/v1/procurement/requisitions/{requisition_id}/reject", schemaName: "ActionReason", visible: (row) => row.status === "submitted" },
            { label: "Cancelar", method: "POST", path: (row) => `/api/v1/procurement/requisitions/${row.id}/cancel`, openApiPath: "/api/v1/procurement/requisitions/{requisition_id}/cancel", schemaName: "ActionReason", visible: (row) => !["cancelled", "approved"].includes(row.status) }
        ] },
    { id: "quotations", group: "Estoque e compras", icon: "⇄", title: "Cotações", description: "Cotações, fornecedores convidados, propostas e adjudicação.", listPath: "/api/v1/procurement/quotations", createPath: "/api/v1/procurement/quotations", detailPath: (row) => `/api/v1/procurement/quotations/${row.id}`, columns: [col("quotation_number", "Número"), col("requisition_id"), col("deadline", "Prazo", "datetime"), col("status")], statusParam: "status" },
    { id: "purchase-orders", group: "Estoque e compras", icon: "▧", title: "Pedidos de compra", description: "Pedidos, aprovação, recebimentos parciais e devoluções.", listPath: "/api/v1/procurement/orders", createPath: "/api/v1/procurement/orders", detailPath: (row) => `/api/v1/procurement/orders/${row.id}`, columns: [col("order_number"), col("supplier_id"), col("total_amount", undefined, "money"), col("status")], statusParam: "status", actions: [{ label: "Aprovar", method: "POST", direct: true, path: (row) => `/api/v1/procurement/orders/${row.id}/approve`, openApiPath: "/api/v1/procurement/orders/{order_id}/approve", visible: (row) => row.status === "draft" }] },
    { id: "inventory-counts", group: "Estoque e compras", icon: "☷", title: "Inventários", description: "Contagens físicas e ajustes compensatórios de estoque.", listPath: "/api/v1/inventory/counts", createPath: "/api/v1/inventory/counts", detailPath: (row) => `/api/v1/inventory/counts/${row.id}`, columns: [col("count_number", "Número"), col("warehouse_id"), col("started_at", "Iniciado em", "datetime"), col("status")], statusParam: "status" },
    { id: "cost-centers", group: "Financeiro", icon: "⌘", title: "Centros de custo", description: "Estrutura analítica para contratos, receitas, despesas e rateios.", listPath: "/api/v1/finance/cost-centers", createPath: "/api/v1/finance/cost-centers", columns: [col("code"), col("name"), col("parent_id"), col("status")], statusParam: "status", actions: [
            { label: "Editar", method: "PATCH", path: (row) => `/api/v1/finance/cost-centers/${row.id}`, openApiPath: "/api/v1/finance/cost-centers/{cost_center_id}", schemaName: "CostCenterUpdate", preset: {} }
        ] },
    { id: "financial-contracts", group: "Financeiro", icon: "▣", title: "Contratos financeiros", description: "Contratos versionados, aprovação, vigência e saldo de faturamento.", listPath: "/api/v1/finance/contracts", createPath: "/api/v1/finance/contracts", detailPath: (row) => `/api/v1/finance/contracts/${row.id}`, columns: [col("contract_number"), col("responsible_person_id"), col("total_amount", undefined, "money"), col("recognized_amount", undefined, "money"), col("status")], statusParam: "status", actions: [
            { label: "Nova versão", method: "POST", path: (row) => `/api/v1/finance/contracts/${row.id}/versions`, openApiPath: "/api/v1/finance/contracts/{contract_id}/versions", schemaName: "FinancialContractVersionCreate", visible: (row) => !["terminated", "cancelled"].includes(row.status) },
            { label: "Aprovar", method: "POST", path: (row) => `/api/v1/finance/contracts/${row.id}/approve`, openApiPath: "/api/v1/finance/contracts/{contract_id}/approve", schemaName: "ContractDecision", visible: (row) => row.status === "draft" },
            { label: "Ativar", method: "POST", path: (row) => `/api/v1/finance/contracts/${row.id}/activate`, openApiPath: "/api/v1/finance/contracts/{contract_id}/activate", schemaName: "ContractDecision", visible: (row) => row.status === "approved" },
            { label: "Encerrar", method: "POST", path: (row) => `/api/v1/finance/contracts/${row.id}/terminate`, openApiPath: "/api/v1/finance/contracts/{contract_id}/terminate", schemaName: "ContractTermination", visible: (row) => ["approved", "active"].includes(row.status) }
        ] },
    { id: "financial-plans", group: "Financeiro", icon: "▦", title: "Planos financeiros", description: "Parcelamento, descontos e geração idempotente de cobranças.", listPath: "/api/v1/finance/plans", createPath: "/api/v1/finance/plans", detailPath: (row) => `/api/v1/finance/plans/${row.id}`, columns: [col("plan_number"), col("contract_id"), col("installment_count", undefined, "number"), col("net_amount", undefined, "money"), col("status")], statusParam: "status", actions: [
            { label: "Gerar cobrança", method: "POST", path: (row) => `/api/v1/finance/plans/${row.id}/generate`, openApiPath: "/api/v1/finance/plans/{plan_id}/generate", schemaName: "PlanGeneration", visible: (row) => row.status === "draft" }
        ] },
    { id: "charges", group: "Financeiro", icon: "▤", title: "Cobranças", description: "Cobranças manuais ou contratuais, itens, parcelas, saldo e cancelamento auditado.", listPath: "/api/v1/finance/charges", createPath: "/api/v1/finance/charges", detailPath: (row) => `/api/v1/finance/charges/${row.id}`, columns: [col("charge_number"), col("due_date", undefined, "date"), col("total_amount", undefined, "money"), col("outstanding_amount", undefined, "money"), col("status")], statusParam: "status", actions: [
            { label: "Cancelar", method: "POST", path: (row) => `/api/v1/finance/charges/${row.id}/cancel`, openApiPath: "/api/v1/finance/charges/{charge_id}/cancel", schemaName: "ChargeCancel", visible: (row) => !["cancelled", "paid"].includes(row.status) }
        ] },
    { id: "installments", group: "Financeiro", icon: "▥", title: "Parcelas e recebíveis", description: "Parcelas, saldos, pagamentos, reembolsos, multas e juros.", listPath: "/api/v1/finance/installments", detailPath: (row) => `/api/v1/finance/installments/${row.id}`, columns: [col("installment_number"), col("due_date", undefined, "date"), col("amount", undefined, "money"), col("outstanding_amount", undefined, "money"), col("status")], statusParam: "status", actions: [
            { label: "Aplicar encargo", method: "POST", path: (row) => `/api/v1/finance/installments/${row.id}/penalties`, openApiPath: "/api/v1/finance/installments/{installment_id}/penalties", schemaName: "PenaltyCreate", visible: (row) => !["cancelled", "paid"].includes(row.status) }
        ] },
    { id: "payments", group: "Financeiro", icon: "◉", title: "Pagamentos", description: "Recebimentos e saídas com alocação explícita, confirmação e reembolso.", listPath: "/api/v1/finance/payments", createPath: "/api/v1/finance/payments", detailPath: (row) => `/api/v1/finance/payments/${row.id}`, columns: [col("payment_number"), col("direction"), col("method"), col("amount", undefined, "money"), col("status")], statusParam: "status", actions: [
            { label: "Confirmar", method: "POST", path: (row) => `/api/v1/finance/payments/${row.id}/confirm`, openApiPath: "/api/v1/finance/payments/{payment_id}/confirm", schemaName: "PaymentConfirm", visible: (row) => row.status === "pending" },
            { label: "Reembolsar", method: "POST", path: (row) => `/api/v1/finance/payments/${row.id}/refunds`, openApiPath: "/api/v1/finance/payments/{payment_id}/refunds", schemaName: "RefundCreate", visible: (row) => row.direction === "incoming" && ["confirmed", "partially_refunded"].includes(row.status) }
        ] },
    { id: "payables", group: "Financeiro", icon: "↘", title: "Contas a pagar", description: "Obrigações, vencimentos e pagamentos parciais ou integrais.", listPath: "/api/v1/finance/payables", createPath: "/api/v1/finance/payables", detailPath: (row) => `/api/v1/finance/payables/${row.id}`, columns: [col("payable_number"), col("description"), col("due_date", undefined, "date"), col("outstanding_amount", undefined, "money"), col("status")], statusParam: "status", actions: [
            { label: "Registrar pagamento", method: "POST", path: (row) => `/api/v1/finance/payables/${row.id}/payments`, openApiPath: "/api/v1/finance/payables/{payable_id}/payments", schemaName: "PayablePaymentCreate", visible: (row) => ["open", "partially_paid"].includes(row.status) }
        ] },
    { id: "scholarships", group: "Financeiro", icon: "★", title: "Bolsas", description: "Benefícios percentuais ou fixos por aluno e matrícula, com vigência.", listPath: "/api/v1/finance/scholarships", createPath: "/api/v1/finance/scholarships", columns: [col("student_id"), col("scholarship_type"), col("percentage", undefined, "number"), col("fixed_amount", undefined, "money"), col("status")], statusParam: "status" },
    { id: "ledger-batches", group: "Financeiro", icon: "≡", title: "Razão financeiro", description: "Lotes imutáveis em partidas dobradas, referências e hashes verificáveis.", listPath: "/api/v1/finance/ledger/batches", detailPath: (row) => `/api/v1/finance/ledger/batches/${row.id}`, columns: [col("batch_number"), col("event_type"), col("total_debit", undefined, "money"), col("total_credit", undefined, "money"), col("occurred_at", undefined, "datetime")] },
    { id: "service-catalogs", group: "Serviços", icon: "▦", title: "Catálogos de serviços", description: "Catálogos por instituição e unidade, com vigência, estado e versionamento.", listPath: "/api/v1/service-catalogs", createPath: "/api/v1/service-catalogs", detailPath: (row) => `/api/v1/service-catalogs/${row.id}`, columns: [col("code"), col("name"), col("valid_from", undefined, "date"), col("valid_until", undefined, "date"), col("status")], statusParam: "status", actions: [
            { label: "Editar", method: "PATCH", path: (row) => `/api/v1/service-catalogs/${row.id}`, openApiPath: "/api/v1/service-catalogs/{catalog_id}", schemaName: "CatalogUpdate", preset: {} }
        ] },
    { id: "services", group: "Serviços", icon: "◇", title: "Serviços", description: "Mensalidades, cursos, transporte, documentos e demais serviços recorrentes ou avulsos.", listPath: "/api/v1/services", createPath: "/api/v1/services", detailPath: (row) => `/api/v1/services/${row.id}`, columns: [col("code"), col("name"), col("service_type"), col("recurrence_type"), col("taxable", undefined, "boolean"), col("status")], statusParam: "status", actions: [
            { label: "Editar", method: "PATCH", path: (row) => `/api/v1/services/${row.id}`, openApiPath: "/api/v1/services/{service_id}", schemaName: "ServiceUpdate", preset: {} },
            { label: "Adicionar variação", method: "POST", path: (row) => `/api/v1/services/${row.id}/variants`, openApiPath: "/api/v1/services/{service_id}/variants", schemaName: "VariantCreate" },
            { label: "Adicionar preço", method: "POST", path: (row) => `/api/v1/services/${row.id}/prices`, openApiPath: "/api/v1/services/{service_id}/prices", schemaName: "PriceTableCreate" },
            { label: "Adicionar regra de cobrança", method: "POST", path: (row) => `/api/v1/services/${row.id}/billing-rules`, openApiPath: "/api/v1/services/{service_id}/billing-rules", schemaName: "BillingRuleCreate" },
            { label: "Adicionar perfil fiscal", method: "POST", path: (row) => `/api/v1/services/${row.id}/fiscal-profiles`, openApiPath: "/api/v1/services/{service_id}/fiscal-profiles", schemaName: "FiscalProfileCreate" }
        ] },
    { id: "service-variants", group: "Serviços", icon: "◈", title: "Variações de serviço", description: "Variações, duração, capacidade e metadados operacionais.", listPath: "/api/v1/service-variants", columns: [col("code"), col("name"), col("service_id"), col("duration_minutes"), col("capacity", undefined, "number"), col("status")], statusParam: "status", actions: [
            { label: "Editar", method: "PATCH", path: (row) => `/api/v1/service-variants/${row.id}`, openApiPath: "/api/v1/service-variants/{variant_id}", schemaName: "VariantUpdate" }
        ] },
    { id: "service-prices", group: "Serviços", icon: "¤", title: "Preços e vigências", description: "Tabelas de preço por serviço e variação, com vigência e periodicidade.", listPath: "/api/v1/service-price-tables", columns: [col("name"), col("service_id"), col("variant_id"), col("amount", undefined, "money"), col("billing_frequency"), col("valid_from", undefined, "date"), col("status")], statusParam: "status" },
    { id: "service-billing-rules", group: "Serviços", icon: "⚙", title: "Regras de cobrança", description: "Gatilho, vencimento, competência, reconhecimento e rateio de serviços.", listPath: "/api/v1/service-billing-rules", columns: [col("code"), col("name"), col("service_id"), col("billing_trigger"), col("due_day", undefined, "number"), col("fiscal_trigger"), col("status")], statusParam: "status" },
    { id: "service-fiscal-profiles", group: "Serviços", icon: "§", title: "Perfis fiscais de serviços", description: "Classificação NBS, LC 116, código municipal, CNAE, ISS e RTC por vigência.", listPath: "/api/v1/service-fiscal-profiles", detailPath: (row) => `/api/v1/service-fiscal-profiles/${row.id}`, columns: [col("service_id"), col("nbs_code"), col("lc116_code"), col("municipal_service_code"), col("cclass_trib"), col("status")], statusParam: "status", actions: [
            { label: "Publicar", method: "POST", path: (row) => `/api/v1/service-fiscal-profiles/${row.id}/publish`, openApiPath: "/api/v1/service-fiscal-profiles/{profile_id}/publish", schemaName: "FiscalProfilePublish", visible: (row) => row.status !== "published" }
        ] },
    { id: "service-subscriptions", group: "Serviços", icon: "↻", title: "Assinaturas de serviços", description: "Serviços recorrentes vinculados a pessoa, matrícula, contrato e competência.", listPath: "/api/v1/service-subscriptions", createPath: "/api/v1/service-subscriptions", detailPath: (row) => `/api/v1/service-subscriptions/${row.id}`, columns: [col("subscription_number"), col("subscriber_person_id"), col("service_id"), col("starts_on", undefined, "date"), col("next_competence_on", undefined, "date"), col("status")], statusParam: "status", actions: [
            { label: "Ativar", method: "POST", path: (row) => `/api/v1/service-subscriptions/${row.id}/activate`, openApiPath: "/api/v1/service-subscriptions/{subscription_id}/activate", schemaName: "SubscriptionDecision", visible: (row) => row.status === "draft" },
            { label: "Suspender", method: "POST", path: (row) => `/api/v1/service-subscriptions/${row.id}/suspend`, openApiPath: "/api/v1/service-subscriptions/{subscription_id}/suspend", schemaName: "SubscriptionDecision", visible: (row) => row.status === "active" },
            { label: "Retomar", method: "POST", path: (row) => `/api/v1/service-subscriptions/${row.id}/resume`, openApiPath: "/api/v1/service-subscriptions/{subscription_id}/resume", schemaName: "SubscriptionDecision", visible: (row) => row.status === "suspended" },
            { label: "Cancelar", method: "POST", path: (row) => `/api/v1/service-subscriptions/${row.id}/cancel`, openApiPath: "/api/v1/service-subscriptions/{subscription_id}/cancel", schemaName: "SubscriptionDecision", visible: (row) => !["cancelled", "completed"].includes(row.status) },
            { label: "Gerar competência", method: "POST", path: (row) => `/api/v1/service-subscriptions/${row.id}/competencies`, openApiPath: "/api/v1/service-subscriptions/{subscription_id}/competencies", schemaName: "CompetenceGenerate", visible: (row) => row.status === "active" }
        ] },
    { id: "service-orders", group: "Serviços", icon: "▤", title: "Pedidos de serviço", description: "Pedido comercial único, cobrança transacional, execução e solicitação fiscal condicionada.", listPath: "/api/v1/service-orders", createPath: "/api/v1/service-orders", detailPath: (row) => `/api/v1/service-orders/${row.id}`, columns: [col("order_number"), col("subscriber_person_id"), col("total_amount", undefined, "money"), col("due_date", undefined, "date"), col("fiscal_status"), col("status")], statusParam: "status", actions: [
            { label: "Confirmar", method: "POST", path: (row) => `/api/v1/service-orders/${row.id}/confirm`, openApiPath: "/api/v1/service-orders/{order_id}/confirm", schemaName: "OrderConfirm", visible: (row) => row.status === "draft" },
            { label: "Iniciar", method: "POST", direct: true, path: (row) => `/api/v1/service-orders/${row.id}/start`, openApiPath: "/api/v1/service-orders/{order_id}/start", visible: (row) => row.status === "confirmed" },
            { label: "Concluir", method: "POST", direct: true, path: (row) => `/api/v1/service-orders/${row.id}/complete`, openApiPath: "/api/v1/service-orders/{order_id}/complete", visible: (row) => row.status === "in_progress" },
            { label: "Cancelar", method: "POST", path: (row) => `/api/v1/service-orders/${row.id}/cancel`, openApiPath: "/api/v1/service-orders/{order_id}/cancel", schemaName: "OrderCancel", visible: (row) => !["cancelled", "completed"].includes(row.status) },
            { label: "Agendar execução", method: "POST", path: (row) => `/api/v1/service-orders/${row.id}/executions`, openApiPath: "/api/v1/service-orders/{order_id}/executions", schemaName: "ExecutionCreate", visible: (row) => ["confirmed", "in_progress"].includes(row.status) }
        ] },
    { id: "service-executions", group: "Serviços", icon: "▶", title: "Execuções de serviço", description: "Agenda, execução parcial ou integral, evidências e cancelamento.", listPath: "/api/v1/service-executions", columns: [col("execution_number"), col("order_id"), col("scheduled_at", undefined, "datetime"), col("quantity", undefined, "number"), col("performer_person_id"), col("status")], statusParam: "status", actions: [
            { label: "Iniciar", method: "POST", path: (row) => `/api/v1/service-executions/${row.id}/start`, openApiPath: "/api/v1/service-executions/{execution_id}/start", schemaName: "ExecutionStart", visible: (row) => row.status === "scheduled" },
            { label: "Concluir", method: "POST", path: (row) => `/api/v1/service-executions/${row.id}/complete`, openApiPath: "/api/v1/service-executions/{execution_id}/complete", schemaName: "ExecutionComplete", visible: (row) => ["scheduled", "in_progress"].includes(row.status) },
            { label: "Cancelar", method: "POST", path: (row) => `/api/v1/service-executions/${row.id}/cancel`, openApiPath: "/api/v1/service-executions/{execution_id}/cancel", schemaName: "ExecutionCancel", visible: (row) => !["cancelled", "completed"].includes(row.status) }
        ] },
    { id: "service-fiscal-events", group: "Serviços", icon: "◇", title: "Eventos fiscais de serviços", description: "Solicitações fiscais classificadas sem representar provider real quando não configurado.", listPath: "/api/v1/service-fiscal-events", columns: [col("event_type"), col("order_id"), col("fiscal_trigger"), col("requested_at", undefined, "datetime"), col("status")], statusParam: "status" },
    { id: "asset-locations", group: "Patrimônio", icon: "⌖", title: "Localizações", description: "Estrutura física e hierárquica de localização patrimonial.", listPath: "/api/v1/asset-locations", createPath: "/api/v1/asset-locations", detailPath: (row) => `/api/v1/asset-locations/${row.id}`, columns: [col("code"), col("name"), col("parent_id"), col("status")], statusParam: "status" },
    { id: "assets", group: "Patrimônio", icon: "◆", title: "Bens patrimoniais", description: "Incorporação, localização, empréstimo, manutenção e depreciação.", listPath: "/api/v1/assets", createPath: "/api/v1/assets", detailPath: (row) => `/api/v1/assets/${row.id}`, columns: [col("asset_number", "Número"), col("tag_number"), col("name"), col("acquisition_value", undefined, "money"), col("status")], searchParam: "search", statusParam: "status" }
];
const dashboardItem = { id: "dashboard", group: "Visão geral", icon: "◫", title: "Dashboard" };
const commonStatuses = ["active", "inactive", "draft", "submitted", "submitted_for_review", "changes_requested", "approved", "rejected", "open", "attendance_open", "attendance_submitted", "closed", "reopened", "scheduled", "in_progress", "partially_executed", "executed", "rescheduled", "completed", "cancelled", "processed", "published", "not_configured", "blocked_validation", "confirmed", "suspended"];
function fieldLabel(name) {
    return fieldLabels[name] ?? name.replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}
function translateStatus(value) {
    return statusLabels[value] ?? value.replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}
function initials(value) {
    const parts = value.trim().split(/\s+/).filter(Boolean);
    return parts.slice(0, 2).map((part) => part[0]?.toUpperCase() ?? "").join("") || "IN";
}
function valueAt(row, path) {
    return path.split(".").reduce((current, key) => current && typeof current === "object" ? current[key] : undefined, row);
}
function statusClass(status) {
    if (["active", "approved", "completed", "closed", "processed", "published", "paid", "healthy", "received"].includes(status))
        return "success";
    if (["rejected", "cancelled", "failed", "terminated", "inactive"].includes(status))
        return "danger";
    if (["draft", "pending", "open", "reopened", "scheduled", "not_configured", "partially_received"].includes(status))
        return "warning";
    return "info";
}
function formatCell(value, format) {
    if (value === null || value === undefined || value === "")
        return "—";
    if (format === "boolean")
        return value ? "Sim" : "Não";
    if (format === "money") {
        const number = Number(value);
        return Number.isFinite(number) ? new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" }).format(number) : String(value);
    }
    if (format === "number") {
        const number = Number(value);
        return Number.isFinite(number) ? new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 4 }).format(number) : String(value);
    }
    if (format === "minutes") {
        const minutes = Number(value);
        if (!Number.isFinite(minutes))
            return String(value);
        return `${Math.floor(minutes / 60)}h ${minutes % 60}min`;
    }
    if (format === "date" || format === "datetime") {
        const date = new Date(String(value));
        if (Number.isNaN(date.getTime()))
            return String(value);
        return new Intl.DateTimeFormat("pt-BR", format === "datetime" ? { dateStyle: "short", timeStyle: "short" } : { dateStyle: "short" }).format(date);
    }
    if (typeof value === "boolean")
        return value ? "Sim" : "Não";
    if (typeof value === "object")
        return JSON.stringify(value);
    const text = String(value);
    return text.length > 72 ? `${text.slice(0, 69)}…` : text;
}
function formatDetail(value) {
    if (value === null || value === undefined || value === "")
        return "—";
    if (typeof value === "boolean")
        return value ? "Sim" : "Não";
    if (typeof value === "object")
        return JSON.stringify(value, null, 2);
    return String(value);
}
function idempotencyKey() {
    return crypto.randomUUID();
}
createApp({
    setup() {
        const api = new ApiClient();
        const booting = ref(true);
        const runtime = ref(null);
        const user = ref(null);
        const authenticated = computed(() => Boolean(user.value && api.accessToken));
        const credentials = reactive({ email: "", password: "", keepSession: true });
        const authLoading = ref(false);
        const authError = ref("");
        const currentRoute = ref("dashboard");
        const sidebarOpen = ref(false);
        const userMenuOpen = ref(false);
        const darkMode = ref(localStorage.getItem("tenant.theme") === "dark");
        const online = ref(navigator.onLine);
        const openApi = ref(null);
        const rows = ref([]);
        const nextCursor = ref(null);
        const searchTerm = ref("");
        const statusFilter = ref("");
        const pageLoading = ref(false);
        const pageError = ref("");
        const dashboard = reactive({ academic: null, attendance: null, finance: null, services: null, hr: null, payroll: null, timekeeping: null });
        const toasts = ref([]);
        const dialog = reactive({ open: false, mode: "details", eyebrow: "", title: "", submitLabel: "Salvar", fields: [], values: {}, error: "", loading: false, endpoint: "", method: "POST", schema: null, detail: null, download: false });
        const activeResource = computed(() => resources.find((item) => item.id === currentRoute.value) ?? null);
        const currentTitle = computed(() => currentRoute.value === "dashboard" ? "Visão geral" : activeResource.value?.title ?? "Administração");
        const currentGroup = computed(() => currentRoute.value === "dashboard" ? "Operação institucional" : activeResource.value?.group ?? "Administração");
        const institutionName = computed(() => runtime.value?.branding.short_name || runtime.value?.institution?.trade_name || "Instituição");
        const initialsComputed = computed(() => initials(institutionName.value));
        const userInitials = computed(() => initials(user.value?.display_name || user.value?.email || "Usuário"));
        const navigationGroups = computed(() => {
            const grouped = new Map();
            grouped.set("Visão geral", [dashboardItem]);
            for (const resource of resources) {
                const items = grouped.get(resource.group) ?? [];
                items.push({ id: resource.id, icon: resource.icon, title: resource.title });
                grouped.set(resource.group, items);
            }
            return Array.from(grouped, ([name, items]) => ({ name, items }));
        });
        const dashboardMetrics = computed(() => [
            { icon: "♟", label: "Alunos ativos", value: dashboard.academic?.students?.active ?? 0 },
            { icon: "✓", label: "Matrículas ativas", value: dashboard.academic?.enrollments?.active ?? 0 },
            { icon: "▤", label: "Turmas ativas", value: dashboard.academic?.classes?.active ?? 0 },
            { icon: "✓", label: "Chamadas pendentes", value: dashboard.attendance?.sessions?.pending_close ?? 0 },
            { icon: "!", label: "Riscos críticos", value: dashboard.attendance?.risks?.critical ?? 0 },
            { icon: "↗", label: "Recebíveis em aberto", value: dashboard.finance?.receivables?.open_amount ?? "0.00" },
            { icon: "↘", label: "Contas a pagar", value: dashboard.finance?.payables?.open_amount ?? "0.00" },
            { icon: "◇", label: "Serviços ativos", value: dashboard.services?.services ?? 0 },
            { icon: "▶", label: "Execuções pendentes", value: dashboard.services?.pending_executions ?? 0 },
            { icon: "♙", label: "Colaboradores ativos", value: dashboard.hr?.employees?.active ?? 0 },
            { icon: "▨", label: "Competências abertas", value: dashboard.payroll?.open_competences ?? 0 },
            { icon: "▶", label: "Folhas pendentes", value: dashboard.payroll?.pending_runs ?? 0 }
        ]);
        const quickActions = [
            { icon: "♟", title: "Alunos", subtitle: "Consultar cadastro acadêmico", route: "students" },
            { icon: "✓", title: "Matrículas", subtitle: "Ativar e movimentar vínculos", route: "enrollments" },
            { icon: "▧", title: "Planejamento", subtitle: "Criar, revisar e executar planos", route: "teaching-plans" },
            { icon: "✓", title: "Chamada", subtitle: "Registrar frequência online ou offline", route: "class-sessions" },
            { icon: "♙", title: "Colaboradores", subtitle: "Consultar quadro funcional", route: "employees" },
            { icon: "●", title: "Marcações", subtitle: "Registrar e consultar ponto", route: "punches" },
            { icon: "▧", title: "Fechar período", subtitle: "Apurar espelhos de ponto", route: "timekeeping-periods" },
            { icon: "▶", title: "Processar folha", subtitle: "Simular ou produzir cálculo", route: "payroll-runs" },
            { icon: "▣", title: "Contratos financeiros", subtitle: "Aprovar e faturar contratos", route: "financial-contracts" },
            { icon: "◉", title: "Pagamentos", subtitle: "Receber e alocar valores", route: "payments" },
            { icon: "↘", title: "Contas a pagar", subtitle: "Registrar obrigações e baixas", route: "payables" },
            { icon: "◇", title: "Catálogo de serviços", subtitle: "Preços, regras e classificação fiscal", route: "services" },
            { icon: "▤", title: "Pedidos de serviço", subtitle: "Cobrar, executar e acompanhar", route: "service-orders" },
            { icon: "↟", title: "Compras", subtitle: "Requisições e aprovações", route: "requisitions" }
        ];
        const detailEntries = computed(() => Object.entries(dialog.detail ?? {}).map(([key, value]) => ({ key, value })));
        function showToast(message, type = "info") {
            const toast = { id: crypto.randomUUID(), message, type };
            toasts.value.push(toast);
            window.setTimeout(() => { toasts.value = toasts.value.filter((item) => item.id !== toast.id); }, 4200);
        }
        function applyTheme() {
            document.documentElement.dataset.theme = darkMode.value ? "dark" : "light";
        }
        function applyTenantBranding(configuration) {
            const root = document.documentElement.style;
            root.setProperty("--tenant-primary", configuration.branding.primary_color || "#006d77");
            root.setProperty("--tenant-secondary", configuration.branding.secondary_color || "#0d1b2a");
            root.setProperty("--tenant-accent", configuration.branding.accent_color || "#f59e0b");
            document.title = `${configuration.branding.short_name || configuration.institution?.trade_name || "Instituição"} — Administração`;
        }
        function toggleTheme() {
            darkMode.value = !darkMode.value;
            localStorage.setItem("tenant.theme", darkMode.value ? "dark" : "light");
            applyTheme();
        }
        function errorMessage(error) {
            if (error instanceof ApiFailure) {
                const fieldErrors = error.problem.errors?.map((item) => `${item.field ? `${fieldLabel(item.field)}: ` : ""}${item.message ?? item.code ?? "Inválido"}`).join(" ");
                return fieldErrors || error.problem.detail || error.message;
            }
            return error instanceof Error ? error.message : "Falha inesperada na operação.";
        }
        async function login() {
            authLoading.value = true;
            authError.value = "";
            try {
                const tokens = await api.request("/api/v1/auth/login", {
                    method: "POST",
                    body: { email: credentials.email, password: credentials.password, device_name: navigator.userAgent.slice(0, 180) },
                    retryAuthentication: false
                });
                api.saveTokens(tokens);
                user.value = tokens.user;
                credentials.password = "";
                await Promise.all([loadOpenApi(), loadDashboard()]);
                navigate("dashboard");
            }
            catch (error) {
                authError.value = errorMessage(error);
                api.clearTokens();
            }
            finally {
                authLoading.value = false;
            }
        }
        async function restoreSession() {
            if (!api.accessToken && !api.refreshToken)
                return;
            try {
                const session = await api.request("/api/v1/auth/me");
                user.value = session.user;
            }
            catch {
                api.clearTokens();
                user.value = null;
            }
        }
        async function logout() {
            userMenuOpen.value = false;
            const refreshToken = api.refreshToken;
            try {
                if (refreshToken && api.accessToken) {
                    await api.request("/api/v1/auth/logout", { method: "POST", body: { refresh_token: refreshToken, all_devices: false }, retryAuthentication: false });
                }
            }
            catch { /* logout local continua seguro */ }
            api.clearTokens();
            user.value = null;
            rows.value = [];
            currentRoute.value = "dashboard";
        }
        async function loadOpenApi() {
            if (openApi.value)
                return;
            openApi.value = await api.request("/api/openapi.json", { retryAuthentication: false });
        }
        async function loadDashboard() {
            pageLoading.value = true;
            pageError.value = "";
            try {
                const [academic, attendance, finance, servicesDashboard, hr, payroll, periods] = await Promise.all([
                    api.request("/api/v1/academic/dashboard"),
                    api.request("/api/v1/attendance/dashboard"),
                    api.request("/api/v1/finance/dashboard"),
                    api.request("/api/v1/services-dashboard"),
                    api.request("/api/v1/hr/dashboard"),
                    api.request("/api/v1/payroll/dashboard"),
                    api.request("/api/v1/timekeeping/periods", { query: { limit: 5 } })
                ]);
                dashboard.academic = academic;
                dashboard.attendance = attendance;
                dashboard.finance = finance;
                dashboard.services = servicesDashboard;
                dashboard.hr = hr;
                dashboard.payroll = payroll;
                dashboard.timekeeping = periods;
            }
            catch (error) {
                pageError.value = errorMessage(error);
            }
            finally {
                pageLoading.value = false;
            }
        }
        function navigate(route) {
            userMenuOpen.value = false;
            sidebarOpen.value = false;
            searchTerm.value = "";
            statusFilter.value = "";
            window.location.hash = route;
            currentRoute.value = route;
            if (route === "dashboard")
                void loadDashboard();
            else
                void reloadResource();
        }
        async function reloadResource() {
            rows.value = [];
            nextCursor.value = null;
            await loadResource(false);
        }
        async function loadResource(append) {
            const resource = activeResource.value;
            if (!resource)
                return;
            pageLoading.value = true;
            pageError.value = "";
            try {
                const query = { limit: 50 };
                if (append && nextCursor.value)
                    query.cursor = nextCursor.value;
                if (resource.searchParam && searchTerm.value)
                    query[resource.searchParam] = searchTerm.value;
                if (resource.statusParam && statusFilter.value)
                    query[resource.statusParam] = statusFilter.value;
                const result = await api.request(resource.listPath, { query });
                const loaded = Array.isArray(result) ? result : Array.isArray(result.items) ? result.items : [];
                rows.value = append ? [...rows.value, ...loaded] : loaded;
                nextCursor.value = typeof result.next_cursor === "string" ? result.next_cursor : null;
            }
            catch (error) {
                pageError.value = errorMessage(error);
            }
            finally {
                pageLoading.value = false;
            }
        }
        async function loadNextPage() { if (nextCursor.value)
            await loadResource(true); }
        function resolveSchema(schema) {
            if (!schema)
                return null;
            if (schema.$ref && openApi.value) {
                const name = String(schema.$ref).split("/").pop();
                return name ? openApi.value.components?.schemas?.[name] ?? null : null;
            }
            return schema;
        }
        function schemaByName(name) {
            return openApi.value?.components?.schemas?.[name] ?? null;
        }
        function operationBodySchema(path, method) {
            const operation = openApi.value?.paths?.[path]?.[method.toLowerCase()];
            const raw = operation?.requestBody?.content?.["application/json"]?.schema;
            return resolveSchema(raw);
        }
        function normalizePropertySchema(raw) {
            if (raw.anyOf) {
                const meaningful = raw.anyOf.find((item) => item.type !== "null") ?? raw.anyOf[0];
                return { ...meaningful, title: raw.title ?? meaningful?.title, default: raw.default ?? meaningful?.default };
            }
            return raw;
        }
        function fieldsFromSchema(schema, preset = {}) {
            if (!schema)
                return [];
            const required = new Set(schema.required ?? []);
            const properties = schema.properties ?? {};
            return Object.entries(properties)
                .filter(([name]) => !["institution_id", "unit_id"].includes(name))
                .map(([name, raw]) => {
                const property = normalizePropertySchema(raw);
                const type = String(property.type ?? "string");
                const kind = type === "integer" || type === "number" ? "number" : type === "boolean" ? "boolean" : type === "object" ? "object" : type === "array" ? "array" : "string";
                let inputType = "text";
                if (kind === "number")
                    inputType = "number";
                if (property.format === "date")
                    inputType = "date";
                if (property.format === "date-time")
                    inputType = "datetime-local";
                if (name.includes("email"))
                    inputType = "email";
                if (name.includes("password"))
                    inputType = "password";
                const multiline = ["description", "reason", "notes", "responsibilities", "requirements"].includes(name);
                const help = kind === "object" ? "Informe um objeto JSON válido." : kind === "array" && property.items?.type === "object" ? "Informe uma lista JSON válida." : kind === "array" ? "Separe os valores por linha ou vírgula." : undefined;
                const placeholder = kind === "object" ? "{}" : kind === "array" && property.items?.type === "object" ? "[]" : undefined;
                const field = {
                    name,
                    label: fieldLabel(name),
                    kind,
                    inputType,
                    required: required.has(name),
                    multiline,
                    schema: property,
                };
                if (property.enum !== undefined)
                    field.enumValues = property.enum;
                if (kind === "number")
                    field.step = type === "integer" ? "1" : "0.01";
                if (placeholder !== undefined)
                    field.placeholder = placeholder;
                if (help !== undefined)
                    field.help = help;
                return field;
            });
        }
        function initialValues(fields, preset = {}) {
            const values = {};
            for (const field of fields) {
                if (Object.prototype.hasOwnProperty.call(preset, field.name))
                    values[field.name] = preset[field.name];
                else if (field.schema.const !== undefined)
                    values[field.name] = field.schema.const;
                else if (field.schema.default !== undefined)
                    values[field.name] = field.schema.default;
                else if (field.kind === "boolean")
                    values[field.name] = false;
                else if (field.kind === "object")
                    values[field.name] = "{}";
                else if (field.kind === "array")
                    values[field.name] = field.schema.items?.type === "object" ? "[]" : "";
                else
                    values[field.name] = "";
            }
            return values;
        }
        function openForm(title, eyebrow, endpoint, method, schema, preset = {}, submitLabel = "Salvar") {
            const fields = fieldsFromSchema(schema, preset);
            Object.assign(dialog, { open: true, mode: "form", title, eyebrow, submitLabel, fields, values: initialValues(fields, preset), error: "", loading: false, endpoint, method, schema, detail: null, download: false });
        }
        async function openCreateDialog() {
            const resource = activeResource.value;
            if (!resource?.createPath)
                return;
            try {
                await loadOpenApi();
                const schema = operationBodySchema(resource.openApiCreatePath ?? resource.createPath, "POST");
                openForm(`Novo: ${resource.title}`, resource.group, resource.createPath, "POST", schema, {}, "Criar registro");
            }
            catch (error) {
                showToast(errorMessage(error), "error");
            }
        }
        async function openDetails(row) {
            const resource = activeResource.value;
            dialog.open = true;
            dialog.mode = "details";
            dialog.eyebrow = resource?.group ?? "Detalhes";
            dialog.title = resource?.title ?? "Registro";
            dialog.detail = row;
            dialog.error = "";
            if (resource?.detailPath) {
                dialog.loading = true;
                try {
                    dialog.detail = await api.request(resource.detailPath(row));
                }
                catch (error) {
                    dialog.error = errorMessage(error);
                }
                finally {
                    dialog.loading = false;
                }
            }
        }
        function closeDialog() {
            if (dialog.loading)
                return;
            dialog.open = false;
            dialog.error = "";
            dialog.detail = null;
        }
        function convertFieldValue(field, value) {
            if (field.kind === "boolean")
                return Boolean(value);
            if (value === "" || value === null || value === undefined)
                return undefined;
            if (field.kind === "number") {
                const parsed = Number(value);
                if (!Number.isFinite(parsed))
                    throw new Error(`${field.label}: informe um número válido.`);
                return field.schema.type === "integer" ? Math.trunc(parsed) : parsed;
            }
            if (field.kind === "object") {
                try {
                    return typeof value === "string" ? JSON.parse(value) : value;
                }
                catch {
                    throw new Error(`${field.label}: informe um objeto JSON válido.`);
                }
            }
            if (field.kind === "array") {
                if (Array.isArray(value))
                    return value;
                const text = String(value).trim();
                if (!text)
                    return [];
                if (text.startsWith("[")) {
                    try {
                        return JSON.parse(text);
                    }
                    catch {
                        throw new Error(`${field.label}: informe uma lista JSON válida.`);
                    }
                }
                return text.split(/[\n,]+/).map((item) => item.trim()).filter(Boolean);
            }
            if (field.inputType === "datetime-local" && typeof value === "string" && value)
                return new Date(value).toISOString();
            return value;
        }
        function formPayload() {
            const payload = {};
            for (const field of dialog.fields) {
                const converted = convertFieldValue(field, dialog.values[field.name]);
                if (converted !== undefined)
                    payload[field.name] = converted;
            }
            if (dialog.schema?.properties?.institution_id && user.value?.institution_id)
                payload.institution_id = user.value.institution_id;
            if (dialog.schema?.properties?.unit_id && user.value?.unit_id)
                payload.unit_id = user.value.unit_id;
            return payload;
        }
        async function submitDialog() {
            dialog.loading = true;
            dialog.error = "";
            try {
                const payload = formPayload();
                await api.request(dialog.endpoint, { method: dialog.method, body: payload, headers: { "Idempotency-Key": idempotencyKey() } });
                showToast("Operação concluída com sucesso.", "success");
                dialog.open = false;
                await reloadResource();
                if (currentRoute.value === "dashboard")
                    await loadDashboard();
            }
            catch (error) {
                dialog.error = errorMessage(error);
            }
            finally {
                dialog.loading = false;
            }
        }
        function visibleActions(row) {
            return (activeResource.value?.actions ?? []).filter((action) => !action.visible || action.visible(row));
        }
        async function executeConfiguredAction(action, row) {
            if (action.download) {
                try {
                    const blob = await api.request(action.path(row), { method: action.method, responseType: "blob" });
                    const url = URL.createObjectURL(blob);
                    const link = document.createElement("a");
                    link.href = url;
                    link.download = `${row.document_number || "documento"}.pdf`;
                    link.click();
                    URL.revokeObjectURL(url);
                    showToast("Download iniciado.", "success");
                }
                catch (error) {
                    showToast(errorMessage(error), "error");
                }
                return;
            }
            if (action.direct) {
                try {
                    await api.request(action.path(row), { method: action.method, headers: { "Idempotency-Key": idempotencyKey() } });
                    showToast(`${action.label}: operação concluída.`, "success");
                    await reloadResource();
                }
                catch (error) {
                    showToast(errorMessage(error), "error");
                }
                return;
            }
            try {
                await loadOpenApi();
                const schema = action.schemaName ? schemaByName(action.schemaName) : operationBodySchema(action.openApiPath, action.method);
                openForm(action.label, activeResource.value?.title ?? "Ação", action.path(row), action.method, schema, action.preset ?? {}, action.label);
            }
            catch (error) {
                showToast(errorMessage(error), "error");
            }
        }
        function openPasswordDialog() {
            userMenuOpen.value = false;
            const schema = {
                type: "object",
                required: ["current_password", "new_password"],
                properties: {
                    current_password: { type: "string", title: "Senha atual" },
                    new_password: { type: "string", title: "Nova senha" }
                }
            };
            fieldLabels.current_password = "Senha atual";
            fieldLabels.new_password = "Nova senha";
            openForm("Alterar senha", "Segurança", "/api/v1/auth/change-password", "POST", schema, {}, "Alterar e revogar sessões");
        }
        function handleHashChange() {
            const route = window.location.hash.replace(/^#\/?/, "") || "dashboard";
            const valid = route === "dashboard" || resources.some((item) => item.id === route);
            currentRoute.value = valid ? route : "dashboard";
            if (!authenticated.value)
                return;
            if (currentRoute.value === "dashboard")
                void loadDashboard();
            else
                void reloadResource();
        }
        onMounted(async () => {
            applyTheme();
            window.addEventListener("online", () => { online.value = true; showToast("Conexão restabelecida.", "success"); });
            window.addEventListener("offline", () => { online.value = false; showToast("Sem conexão. Alterações não serão enviadas.", "error"); });
            window.addEventListener("hashchange", handleHashChange);
            try {
                runtime.value = await api.request("/api/v1/auth/runtime", { retryAuthentication: false });
                applyTenantBranding(runtime.value);
                await restoreSession();
                if (authenticated.value) {
                    await loadOpenApi();
                    handleHashChange();
                }
            }
            catch (error) {
                authError.value = errorMessage(error);
            }
            finally {
                booting.value = false;
            }
        });
        return {
            booting, runtime, user, authenticated, credentials, authLoading, authError, currentRoute, sidebarOpen, userMenuOpen,
            darkMode, online, rows, nextCursor, searchTerm, statusFilter, pageLoading, pageError, dashboard, toasts, dialog,
            activeResource, currentTitle, currentGroup, institutionName, initials: initialsComputed, userInitials, navigationGroups,
            dashboardMetrics, quickActions, detailEntries, commonStatuses, login, logout, navigate, toggleTheme, loadDashboard,
            reloadResource, loadNextPage, openCreateDialog, openDetails, closeDialog, submitDialog, visibleActions,
            executeConfiguredAction, openPasswordDialog, translateStatus, statusClass, fieldLabel, valueAt, formatCell, formatDetail
        };
    }
}).mount("#app");
