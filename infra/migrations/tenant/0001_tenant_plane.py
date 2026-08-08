"""Tenant Plane físico e relacional do PIGE360.

Revision ID: 0001_tenant
Revises:
"""
from alembic import op

revision = "0001_tenant"
down_revision = None
branch_labels = ("tenant",)
depends_on = None

SQL = r"""
CREATE TABLE IF NOT EXISTS tenant_metadata (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    person_id TEXT,
    email TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    roles_json TEXT NOT NULL,
    active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(tenant_id, email)
);

CREATE TABLE IF NOT EXISTS refresh_tokens (
    jti TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    tenant_id TEXT NOT NULL,
    token_hash TEXT NOT NULL UNIQUE,
    expires_at TEXT NOT NULL,
    revoked_at TEXT,
    replaced_by TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS idempotency_keys (
    scope TEXT NOT NULL,
    idempotency_key TEXT NOT NULL,
    request_hash TEXT NOT NULL,
    response_json TEXT NOT NULL,
    status_code INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY(scope, idempotency_key)
);

CREATE TABLE IF NOT EXISTS audit_log (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    actor_id TEXT,
    action TEXT NOT NULL,
    aggregate_type TEXT NOT NULL,
    aggregate_id TEXT,
    before_json TEXT,
    after_json TEXT,
    reason TEXT,
    correlation_id TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS outbox_events (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    event_version INTEGER NOT NULL DEFAULT 1,
    aggregate_type TEXT NOT NULL,
    aggregate_id TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    correlation_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    published_at TEXT,
    attempts INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS brand_kits (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    state TEXT NOT NULL,
    active_version INTEGER,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(tenant_id)
);
CREATE TABLE IF NOT EXISTS brand_versions (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    brand_kit_id TEXT NOT NULL REFERENCES brand_kits(id),
    version INTEGER NOT NULL,
    state TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    sha256 TEXT NOT NULL,
    created_by TEXT,
    created_at TEXT NOT NULL,
    UNIQUE(brand_kit_id, version)
);
CREATE TABLE IF NOT EXISTS brand_assets (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    brand_kit_id TEXT NOT NULL REFERENCES brand_kits(id),
    category TEXT NOT NULL,
    original_filename TEXT NOT NULL,
    storage_key TEXT NOT NULL,
    mime_type TEXT NOT NULL,
    bytes INTEGER NOT NULL,
    width INTEGER,
    height INTEGER,
    sha256 TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(tenant_id, sha256, category)
);

CREATE TABLE IF NOT EXISTS tenant_app_manifests (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    version INTEGER NOT NULL,
    state TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    sha256 TEXT NOT NULL,
    created_by TEXT,
    created_at TEXT NOT NULL,
    UNIQUE(tenant_id, version)
);
CREATE TABLE IF NOT EXISTS app_build_requests (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    manifest_id TEXT NOT NULL REFERENCES tenant_app_manifests(id),
    status TEXT NOT NULL,
    requested_platforms_json TEXT NOT NULL,
    result_json TEXT,
    idempotency_key TEXT NOT NULL,
    created_by TEXT,
    created_at TEXT NOT NULL,
    started_at TEXT,
    finished_at TEXT,
    UNIQUE(tenant_id, idempotency_key)
);

CREATE TABLE IF NOT EXISTS teaching_plans (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    institution_id TEXT NOT NULL,
    unit_id TEXT NOT NULL,
    academic_period_id TEXT NOT NULL,
    program_id TEXT,
    curriculum_id TEXT NOT NULL,
    class_group_id TEXT NOT NULL,
    component_id TEXT NOT NULL,
    title TEXT NOT NULL,
    plan_type TEXT NOT NULL,
    start_date TEXT NOT NULL,
    end_date TEXT NOT NULL,
    status TEXT NOT NULL,
    current_version INTEGER NOT NULL,
    approval_required INTEGER NOT NULL DEFAULT 1,
    payload_json TEXT NOT NULL,
    created_by TEXT NOT NULL,
    updated_by TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS teaching_plan_versions (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    teaching_plan_id TEXT NOT NULL REFERENCES teaching_plans(id),
    version INTEGER NOT NULL,
    status TEXT NOT NULL,
    snapshot_json TEXT NOT NULL,
    change_reason TEXT,
    created_by TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(teaching_plan_id, version)
);
CREATE TABLE IF NOT EXISTS teaching_plan_approvals (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    teaching_plan_id TEXT NOT NULL REFERENCES teaching_plans(id),
    version INTEGER NOT NULL,
    decision TEXT NOT NULL,
    comments TEXT,
    actor_id TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS lesson_plans (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    teaching_plan_id TEXT REFERENCES teaching_plans(id),
    class_group_id TEXT NOT NULL,
    component_id TEXT NOT NULL,
    scheduled_start TEXT NOT NULL,
    scheduled_end TEXT NOT NULL,
    status TEXT NOT NULL,
    current_version INTEGER NOT NULL,
    payload_json TEXT NOT NULL,
    created_by TEXT NOT NULL,
    updated_by TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS lesson_plan_versions (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    lesson_plan_id TEXT NOT NULL REFERENCES lesson_plans(id),
    version INTEGER NOT NULL,
    status TEXT NOT NULL,
    snapshot_json TEXT NOT NULL,
    created_by TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(lesson_plan_id, version)
);
CREATE TABLE IF NOT EXISTS lesson_plan_execution_records (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    lesson_plan_id TEXT NOT NULL REFERENCES lesson_plans(id),
    execution_status TEXT NOT NULL,
    completion_percentage INTEGER NOT NULL,
    planned_content_json TEXT NOT NULL,
    delivered_content_json TEXT NOT NULL,
    pending_content_json TEXT NOT NULL,
    additional_content_json TEXT NOT NULL,
    notes TEXT,
    executed_by TEXT NOT NULL,
    executed_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS attendance_policies (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    name TEXT NOT NULL,
    status TEXT NOT NULL,
    current_version INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS attendance_policy_versions (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    policy_id TEXT NOT NULL REFERENCES attendance_policies(id),
    version INTEGER NOT NULL,
    effective_from TEXT NOT NULL,
    effective_until TEXT,
    minimum_percentage TEXT NOT NULL,
    status_effects_json TEXT NOT NULL,
    tolerances_json TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    created_by TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(policy_id, version)
);
CREATE TABLE IF NOT EXISTS class_sessions (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    institution_id TEXT NOT NULL,
    unit_id TEXT NOT NULL,
    class_group_id TEXT NOT NULL,
    component_id TEXT NOT NULL,
    attendance_policy_id TEXT NOT NULL REFERENCES attendance_policies(id),
    lesson_plan_id TEXT REFERENCES lesson_plans(id),
    scheduled_start TEXT NOT NULL,
    scheduled_end TEXT NOT NULL,
    actual_start TEXT,
    actual_end TEXT,
    status TEXT NOT NULL,
    modality TEXT NOT NULL,
    enrolled_students_json TEXT NOT NULL,
    teacher_ids_json TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    version INTEGER NOT NULL DEFAULT 1,
    created_by TEXT NOT NULL,
    updated_by TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS attendance_calls (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    class_session_id TEXT NOT NULL REFERENCES class_sessions(id),
    status TEXT NOT NULL,
    current_version INTEGER NOT NULL,
    mode TEXT NOT NULL,
    opened_by TEXT NOT NULL,
    opened_at TEXT NOT NULL,
    submitted_by TEXT,
    submitted_at TEXT,
    closed_by TEXT,
    closed_at TEXT,
    UNIQUE(class_session_id)
);
CREATE TABLE IF NOT EXISTS attendance_call_versions (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    attendance_call_id TEXT NOT NULL REFERENCES attendance_calls(id),
    version INTEGER NOT NULL,
    snapshot_json TEXT NOT NULL,
    actor_id TEXT NOT NULL,
    origin TEXT NOT NULL,
    device_id TEXT,
    created_at TEXT NOT NULL,
    UNIQUE(attendance_call_id, version)
);
CREATE TABLE IF NOT EXISTS attendance_records (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    attendance_call_id TEXT NOT NULL REFERENCES attendance_calls(id),
    class_session_id TEXT NOT NULL REFERENCES class_sessions(id),
    student_id TEXT NOT NULL,
    status_code TEXT NOT NULL,
    minutes_present INTEGER,
    observation TEXT,
    version INTEGER NOT NULL DEFAULT 1,
    updated_by TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(class_session_id, student_id)
);
CREATE TABLE IF NOT EXISTS attendance_record_events (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    attendance_record_id TEXT NOT NULL REFERENCES attendance_records(id),
    event_type TEXT NOT NULL,
    before_json TEXT,
    after_json TEXT NOT NULL,
    reason TEXT,
    actor_id TEXT NOT NULL,
    origin TEXT NOT NULL,
    device_id TEXT,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS attendance_justifications (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    student_id TEXT NOT NULL,
    session_ids_json TEXT NOT NULL,
    reason TEXT NOT NULL,
    state TEXT NOT NULL,
    attachments_json TEXT NOT NULL,
    submitted_by TEXT NOT NULL,
    reviewed_by TEXT,
    review_notes TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS attendance_corrections (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    attendance_record_id TEXT NOT NULL REFERENCES attendance_records(id),
    from_status TEXT NOT NULL,
    to_status TEXT NOT NULL,
    reason TEXT NOT NULL,
    actor_id TEXT NOT NULL,
    approved_by TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS contract_snapshots (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    contract_id TEXT NOT NULL,
    template_version_id TEXT,
    schema_version INTEGER NOT NULL,
    rendered_variables_json TEXT NOT NULL,
    source_references_json TEXT NOT NULL,
    generated_document_sha256 TEXT NOT NULL,
    storage_key TEXT NOT NULL,
    generated_at TEXT NOT NULL,
    generated_by TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS signature_envelopes (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    contract_id TEXT NOT NULL,
    document_sha256 TEXT NOT NULL,
    state TEXT NOT NULL,
    signing_order TEXT NOT NULL,
    signers_json TEXT NOT NULL,
    evidence_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_tenant_outbox_pending ON outbox_events(published_at, created_at);
CREATE INDEX IF NOT EXISTS idx_teaching_plans_scope ON teaching_plans(tenant_id, class_group_id, component_id, status);
CREATE INDEX IF NOT EXISTS idx_lesson_plans_schedule ON lesson_plans(tenant_id, scheduled_start, status);
CREATE INDEX IF NOT EXISTS idx_sessions_schedule ON class_sessions(tenant_id, scheduled_start, status);
CREATE INDEX IF NOT EXISTS idx_attendance_student ON attendance_records(tenant_id, student_id, status_code);

-- App Factory operacional: entitlements, jobs imutáveis, artifacts e releases.
CREATE TABLE IF NOT EXISTS tenant_app_entitlements (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    app_product TEXT NOT NULL,
    state TEXT NOT NULL,
    valid_from TEXT NOT NULL,
    valid_until TEXT,
    contract_reference TEXT,
    created_by TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(tenant_id, app_product)
);

CREATE TABLE IF NOT EXISTS app_build_jobs (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    build_request_id TEXT NOT NULL REFERENCES app_build_requests(id),
    manifest_id TEXT NOT NULL REFERENCES tenant_app_manifests(id),
    app_product TEXT NOT NULL,
    platform TEXT NOT NULL,
    architecture TEXT NOT NULL,
    status TEXT NOT NULL,
    required_os TEXT NOT NULL,
    spec_sha256 TEXT NOT NULL,
    spec_json TEXT NOT NULL,
    claimed_by TEXT,
    claimed_at TEXT,
    started_at TEXT,
    finished_at TEXT,
    attempts INTEGER NOT NULL DEFAULT 0,
    last_error TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(build_request_id, app_product, platform, architecture)
);
CREATE INDEX IF NOT EXISTS idx_app_build_jobs_queue ON app_build_jobs(status, required_os, created_at);

CREATE TABLE IF NOT EXISTS app_build_artifacts (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    build_request_id TEXT NOT NULL REFERENCES app_build_requests(id),
    build_job_id TEXT NOT NULL REFERENCES app_build_jobs(id),
    app_product TEXT NOT NULL,
    platform TEXT NOT NULL,
    architecture TEXT NOT NULL,
    artifact_kind TEXT NOT NULL,
    filename TEXT NOT NULL,
    storage_key TEXT NOT NULL,
    mime_type TEXT NOT NULL,
    bytes INTEGER NOT NULL,
    sha256 TEXT NOT NULL,
    signed_state TEXT NOT NULL,
    sbom_storage_key TEXT,
    provenance_storage_key TEXT,
    created_at TEXT NOT NULL,
    UNIQUE(tenant_id, sha256, artifact_kind)
);

CREATE TABLE IF NOT EXISTS app_releases (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    build_request_id TEXT NOT NULL REFERENCES app_build_requests(id),
    version TEXT NOT NULL,
    channel TEXT NOT NULL,
    state TEXT NOT NULL,
    changelog TEXT,
    mandatory INTEGER NOT NULL DEFAULT 0,
    created_by TEXT,
    created_at TEXT NOT NULL,
    published_at TEXT,
    revoked_at TEXT,
    revoke_reason TEXT,
    UNIQUE(tenant_id, version, channel)
);

CREATE TABLE IF NOT EXISTS app_release_artifacts (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    release_id TEXT NOT NULL REFERENCES app_releases(id),
    artifact_id TEXT NOT NULL REFERENCES app_build_artifacts(id),
    created_at TEXT NOT NULL,
    UNIQUE(release_id, artifact_id)
);

CREATE TABLE IF NOT EXISTS app_download_events (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    release_id TEXT NOT NULL REFERENCES app_releases(id),
    artifact_id TEXT NOT NULL REFERENCES app_build_artifacts(id),
    user_id TEXT,
    ip TEXT,
    user_agent TEXT,
    created_at TEXT NOT NULL
);

-- PIGE360 V8 - núcleo operacional relacional local (SQLite).
-- Todas as tabelas operacionais possuem tenant_id explícito; o adaptador PostgreSQL
-- aplica RLS e database/role exclusivos por tenant na execução de produção.

CREATE TABLE IF NOT EXISTS institutions (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, legal_name TEXT NOT NULL, trade_name TEXT NOT NULL,
  cnpj TEXT, education_system TEXT, state TEXT NOT NULL DEFAULT 'active',
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL, UNIQUE(tenant_id, cnpj)
);
CREATE TABLE IF NOT EXISTS units (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, institution_id TEXT NOT NULL REFERENCES institutions(id),
  code TEXT NOT NULL, name TEXT NOT NULL, timezone TEXT NOT NULL DEFAULT 'America/Bahia', address_json TEXT NOT NULL DEFAULT '{}',
  state TEXT NOT NULL DEFAULT 'active', created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
  UNIQUE(tenant_id, code)
);
CREATE TABLE IF NOT EXISTS academic_years (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, institution_id TEXT NOT NULL REFERENCES institutions(id),
  name TEXT NOT NULL, starts_on TEXT NOT NULL, ends_on TEXT NOT NULL, state TEXT NOT NULL DEFAULT 'draft',
  version INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
  UNIQUE(tenant_id, institution_id, name)
);
CREATE TABLE IF NOT EXISTS programs (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, institution_id TEXT NOT NULL REFERENCES institutions(id),
  code TEXT NOT NULL, name TEXT NOT NULL, education_level TEXT NOT NULL, modality TEXT,
  state TEXT NOT NULL DEFAULT 'active', created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
  UNIQUE(tenant_id, code)
);
CREATE TABLE IF NOT EXISTS curricula (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, program_id TEXT NOT NULL REFERENCES programs(id),
  code TEXT NOT NULL, name TEXT NOT NULL, version INTEGER NOT NULL DEFAULT 1,
  effective_from TEXT NOT NULL, effective_until TEXT, state TEXT NOT NULL DEFAULT 'active',
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL, UNIQUE(tenant_id, program_id, code, version)
);
CREATE TABLE IF NOT EXISTS curriculum_components (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, curriculum_id TEXT NOT NULL REFERENCES curricula(id),
  code TEXT NOT NULL, name TEXT NOT NULL, workload_hours NUMERIC NOT NULL DEFAULT 0,
  credits NUMERIC, syllabus TEXT, state TEXT NOT NULL DEFAULT 'active',
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL, UNIQUE(tenant_id, curriculum_id, code)
);
CREATE TABLE IF NOT EXISTS class_groups (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, unit_id TEXT NOT NULL REFERENCES units(id),
  academic_year_id TEXT NOT NULL REFERENCES academic_years(id), program_id TEXT NOT NULL REFERENCES programs(id),
  curriculum_id TEXT NOT NULL REFERENCES curricula(id), code TEXT NOT NULL, name TEXT NOT NULL,
  shift TEXT, capacity INTEGER, room TEXT, state TEXT NOT NULL DEFAULT 'active',
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL, UNIQUE(tenant_id, academic_year_id, code)
);

CREATE TABLE IF NOT EXISTS people (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, full_name TEXT NOT NULL, social_name TEXT,
  cpf TEXT, birth_date TEXT, email TEXT, phone TEXT, civil_data_json TEXT NOT NULL DEFAULT '{}',
  address_json TEXT NOT NULL DEFAULT '{}', emergency_json TEXT NOT NULL DEFAULT '{}', state TEXT NOT NULL DEFAULT 'active',
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL, UNIQUE(tenant_id, cpf)
);
CREATE INDEX IF NOT EXISTS ix_people_name ON people(tenant_id, full_name);
CREATE TABLE IF NOT EXISTS students (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, person_id TEXT NOT NULL REFERENCES people(id),
  registration_number TEXT NOT NULL, state TEXT NOT NULL DEFAULT 'active', needs_json TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
  UNIQUE(tenant_id, registration_number), UNIQUE(tenant_id, person_id)
);
CREATE TABLE IF NOT EXISTS guardians (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, person_id TEXT NOT NULL REFERENCES people(id),
  state TEXT NOT NULL DEFAULT 'active', created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
  UNIQUE(tenant_id, person_id)
);
CREATE TABLE IF NOT EXISTS guardian_students (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, guardian_id TEXT NOT NULL REFERENCES guardians(id),
  student_id TEXT NOT NULL REFERENCES students(id), relationship TEXT NOT NULL,
  is_legal INTEGER NOT NULL DEFAULT 0, is_financial INTEGER NOT NULL DEFAULT 0, pickup_authorized INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL, UNIQUE(tenant_id, guardian_id, student_id)
);
CREATE TABLE IF NOT EXISTS employees (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, person_id TEXT NOT NULL REFERENCES people(id),
  employee_number TEXT NOT NULL, department TEXT, position TEXT, admission_date TEXT, state TEXT NOT NULL DEFAULT 'active',
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
  UNIQUE(tenant_id, employee_number), UNIQUE(tenant_id, person_id)
);
CREATE TABLE IF NOT EXISTS teacher_assignments (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, employee_id TEXT NOT NULL REFERENCES employees(id),
  class_group_id TEXT NOT NULL REFERENCES class_groups(id), component_id TEXT NOT NULL REFERENCES curriculum_components(id),
  starts_on TEXT NOT NULL, ends_on TEXT, role TEXT NOT NULL DEFAULT 'teacher', state TEXT NOT NULL DEFAULT 'active',
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
  UNIQUE(tenant_id, employee_id, class_group_id, component_id, starts_on)
);
CREATE TABLE IF NOT EXISTS admission_candidates (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, person_id TEXT NOT NULL REFERENCES people(id),
  program_id TEXT NOT NULL REFERENCES programs(id), academic_year_id TEXT NOT NULL REFERENCES academic_years(id),
  source TEXT, score NUMERIC, rank_position INTEGER, state TEXT NOT NULL DEFAULT 'registered',
  notes TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS enrollments (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, student_id TEXT NOT NULL REFERENCES students(id),
  institution_id TEXT NOT NULL REFERENCES institutions(id), unit_id TEXT NOT NULL REFERENCES units(id),
  program_id TEXT NOT NULL REFERENCES programs(id), curriculum_id TEXT NOT NULL REFERENCES curricula(id),
  academic_year_id TEXT NOT NULL REFERENCES academic_years(id), class_group_id TEXT REFERENCES class_groups(id),
  enrollment_number TEXT NOT NULL, financial_responsible_guardian_id TEXT REFERENCES guardians(id),
  state TEXT NOT NULL DEFAULT 'pre_enrolled', enrolled_on TEXT, ended_on TEXT, version INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL, UNIQUE(tenant_id, enrollment_number)
);
CREATE INDEX IF NOT EXISTS ix_enrollments_student ON enrollments(tenant_id, student_id, state);

CREATE TABLE IF NOT EXISTS financial_contracts (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, enrollment_id TEXT REFERENCES enrollments(id),
  responsible_guardian_id TEXT REFERENCES guardians(id), description TEXT NOT NULL, total_amount NUMERIC NOT NULL,
  currency TEXT NOT NULL DEFAULT 'BRL', competence_rule TEXT NOT NULL DEFAULT 'billing', state TEXT NOT NULL DEFAULT 'draft',
  version INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS installments (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, financial_contract_id TEXT NOT NULL REFERENCES financial_contracts(id),
  sequence INTEGER NOT NULL, competence TEXT, due_date TEXT NOT NULL, original_amount NUMERIC NOT NULL,
  discount_amount NUMERIC NOT NULL DEFAULT 0, penalty_amount NUMERIC NOT NULL DEFAULT 0, interest_amount NUMERIC NOT NULL DEFAULT 0,
  paid_amount NUMERIC NOT NULL DEFAULT 0, state TEXT NOT NULL DEFAULT 'open', created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
  UNIQUE(financial_contract_id, sequence)
);
CREATE INDEX IF NOT EXISTS ix_installments_due ON installments(tenant_id, state, due_date);
CREATE TABLE IF NOT EXISTS payments (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, method TEXT NOT NULL, amount NUMERIC NOT NULL, paid_at TEXT NOT NULL,
  external_reference TEXT, state TEXT NOT NULL DEFAULT 'confirmed', idempotency_key TEXT,
  metadata_json TEXT NOT NULL DEFAULT '{}', created_at TEXT NOT NULL,
  UNIQUE(tenant_id, idempotency_key)
);
CREATE TABLE IF NOT EXISTS payment_allocations (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, payment_id TEXT NOT NULL REFERENCES payments(id),
  installment_id TEXT NOT NULL REFERENCES installments(id), amount NUMERIC NOT NULL, created_at TEXT NOT NULL,
  UNIQUE(payment_id, installment_id)
);
CREATE TABLE IF NOT EXISTS ledger_entries (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, entry_type TEXT NOT NULL, reference_type TEXT NOT NULL, reference_id TEXT NOT NULL,
  debit_account TEXT, credit_account TEXT, amount NUMERIC NOT NULL, competence TEXT, occurred_at TEXT NOT NULL,
  reversal_of_id TEXT REFERENCES ledger_entries(id), description TEXT, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS bank_accounts (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, name TEXT NOT NULL, bank_code TEXT, branch TEXT, account_number TEXT,
  pix_key TEXT, pix_receiver_name TEXT, pix_receiver_city TEXT, state TEXT NOT NULL DEFAULT 'active',
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS pix_charges (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, bank_account_id TEXT NOT NULL REFERENCES bank_accounts(id),
  installment_id TEXT NOT NULL REFERENCES installments(id), txid TEXT NOT NULL, amount NUMERIC NOT NULL,
  br_code TEXT NOT NULL, state TEXT NOT NULL DEFAULT 'pending', expires_at TEXT, paid_at TEXT,
  end_to_end_id TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL, UNIQUE(tenant_id, txid)
);
CREATE TABLE IF NOT EXISTS bank_imports (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, bank_account_id TEXT NOT NULL REFERENCES bank_accounts(id),
  source_type TEXT NOT NULL, source_sha256 TEXT NOT NULL, imported_at TEXT NOT NULL, created_by TEXT,
  UNIQUE(tenant_id, source_sha256)
);
CREATE TABLE IF NOT EXISTS bank_transactions (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, bank_import_id TEXT REFERENCES bank_imports(id),
  bank_account_id TEXT NOT NULL REFERENCES bank_accounts(id), external_id TEXT, posted_at TEXT NOT NULL,
  description TEXT, amount NUMERIC NOT NULL, direction TEXT NOT NULL, state TEXT NOT NULL DEFAULT 'unmatched',
  payment_id TEXT REFERENCES payments(id), created_at TEXT NOT NULL,
  UNIQUE(tenant_id, bank_account_id, external_id)
);

CREATE TABLE IF NOT EXISTS services (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, code TEXT NOT NULL, name TEXT NOT NULL, description TEXT,
  price NUMERIC NOT NULL DEFAULT 0, recurrence TEXT, nbs TEXT, lc116_code TEXT, municipal_code TEXT, cnae TEXT,
  fiscal_profile_json TEXT NOT NULL DEFAULT '{}', state TEXT NOT NULL DEFAULT 'active',
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL, UNIQUE(tenant_id, code)
);
CREATE TABLE IF NOT EXISTS service_orders (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, enrollment_id TEXT REFERENCES enrollments(id),
  responsible_guardian_id TEXT REFERENCES guardians(id), competence TEXT, state TEXT NOT NULL DEFAULT 'draft',
  total_amount NUMERIC NOT NULL DEFAULT 0, financial_contract_id TEXT REFERENCES financial_contracts(id),
  fiscal_document_id TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS service_order_items (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, service_order_id TEXT NOT NULL REFERENCES service_orders(id),
  service_id TEXT NOT NULL REFERENCES services(id), quantity NUMERIC NOT NULL, unit_price NUMERIC NOT NULL,
  total_amount NUMERIC NOT NULL, created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS products (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, sku TEXT NOT NULL, barcode TEXT, name TEXT NOT NULL,
  product_type TEXT NOT NULL DEFAULT 'product', ncm TEXT, cest TEXT, unit TEXT NOT NULL DEFAULT 'UN',
  cost NUMERIC NOT NULL DEFAULT 0, sale_price NUMERIC NOT NULL DEFAULT 0, fiscal_profile_json TEXT NOT NULL DEFAULT '{}',
  allergen_json TEXT NOT NULL DEFAULT '[]', restriction_json TEXT NOT NULL DEFAULT '{}', state TEXT NOT NULL DEFAULT 'active',
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL, UNIQUE(tenant_id, sku), UNIQUE(tenant_id, barcode)
);
CREATE TABLE IF NOT EXISTS stock_balances (
  tenant_id TEXT NOT NULL, product_id TEXT NOT NULL REFERENCES products(id), warehouse TEXT NOT NULL DEFAULT 'default',
  quantity NUMERIC NOT NULL DEFAULT 0, reserved NUMERIC NOT NULL DEFAULT 0, updated_at TEXT NOT NULL,
  PRIMARY KEY(tenant_id, product_id, warehouse)
);
CREATE TABLE IF NOT EXISTS stock_movements (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, product_id TEXT NOT NULL REFERENCES products(id), warehouse TEXT NOT NULL DEFAULT 'default',
  movement_type TEXT NOT NULL, quantity NUMERIC NOT NULL, unit_cost NUMERIC, reference_type TEXT, reference_id TEXT,
  reason TEXT, occurred_at TEXT NOT NULL, created_by TEXT
);
CREATE TABLE IF NOT EXISTS cash_sessions (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, terminal_code TEXT NOT NULL, operator_user_id TEXT NOT NULL,
  opened_at TEXT NOT NULL, opening_amount NUMERIC NOT NULL DEFAULT 0, closed_at TEXT, closing_amount NUMERIC,
  state TEXT NOT NULL DEFAULT 'open', created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS sales (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, cash_session_id TEXT REFERENCES cash_sessions(id),
  customer_person_id TEXT REFERENCES people(id), student_id TEXT REFERENCES students(id), channel TEXT NOT NULL,
  subtotal NUMERIC NOT NULL, discount NUMERIC NOT NULL DEFAULT 0, total_amount NUMERIC NOT NULL,
  state TEXT NOT NULL DEFAULT 'completed', fiscal_status TEXT NOT NULL DEFAULT 'pending', idempotency_key TEXT,
  created_by TEXT NOT NULL, created_at TEXT NOT NULL, UNIQUE(tenant_id, idempotency_key)
);
CREATE TABLE IF NOT EXISTS sale_items (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, sale_id TEXT NOT NULL REFERENCES sales(id),
  product_id TEXT NOT NULL REFERENCES products(id), quantity NUMERIC NOT NULL, unit_price NUMERIC NOT NULL,
  discount NUMERIC NOT NULL DEFAULT 0, total_amount NUMERIC NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS sale_payments (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, sale_id TEXT NOT NULL REFERENCES sales(id),
  method TEXT NOT NULL, amount NUMERIC NOT NULL, external_reference TEXT, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS suppliers (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, legal_name TEXT NOT NULL, trade_name TEXT, cnpj TEXT,
  email TEXT, phone TEXT, state TEXT NOT NULL DEFAULT 'active', created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
  UNIQUE(tenant_id, cnpj)
);
CREATE TABLE IF NOT EXISTS purchase_orders (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, supplier_id TEXT NOT NULL REFERENCES suppliers(id),
  order_number TEXT NOT NULL, state TEXT NOT NULL DEFAULT 'draft', total_amount NUMERIC NOT NULL DEFAULT 0,
  expected_on TEXT, received_at TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
  UNIQUE(tenant_id, order_number)
);
CREATE TABLE IF NOT EXISTS purchase_order_items (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, purchase_order_id TEXT NOT NULL REFERENCES purchase_orders(id),
  product_id TEXT NOT NULL REFERENCES products(id), quantity NUMERIC NOT NULL, unit_cost NUMERIC NOT NULL,
  received_quantity NUMERIC NOT NULL DEFAULT 0, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS assets (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, asset_number TEXT NOT NULL, description TEXT NOT NULL,
  acquisition_date TEXT, acquisition_cost NUMERIC, location TEXT, responsible_person_id TEXT REFERENCES people(id),
  state TEXT NOT NULL DEFAULT 'active', created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
  UNIQUE(tenant_id, asset_number)
);

CREATE TABLE IF NOT EXISTS fiscal_profiles (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, establishment_name TEXT NOT NULL, cnpj TEXT NOT NULL,
  tax_regime TEXT NOT NULL, uf TEXT NOT NULL, municipality_code TEXT, environment TEXT NOT NULL DEFAULT 'homologation',
  state TEXT NOT NULL DEFAULT 'active', created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
  UNIQUE(tenant_id, cnpj)
);
CREATE TABLE IF NOT EXISTS fiscal_rules (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, fiscal_profile_id TEXT NOT NULL REFERENCES fiscal_profiles(id),
  operation_type TEXT NOT NULL, item_kind TEXT NOT NULL, classification_key TEXT,
  effective_from TEXT NOT NULL, effective_until TEXT, rules_json TEXT NOT NULL,
  state TEXT NOT NULL DEFAULT 'active', version INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS fiscal_documents (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, fiscal_profile_id TEXT REFERENCES fiscal_profiles(id),
  document_type TEXT NOT NULL, source_type TEXT NOT NULL, source_id TEXT NOT NULL, environment TEXT NOT NULL,
  state TEXT NOT NULL DEFAULT 'requested', access_key TEXT, protocol TEXT, number TEXT, series TEXT,
  totals_json TEXT NOT NULL DEFAULT '{}', request_json TEXT NOT NULL DEFAULT '{}', response_json TEXT NOT NULL DEFAULT '{}',
  xml_storage_key TEXT, pdf_storage_key TEXT, xml_sha256 TEXT, error_code TEXT, error_message TEXT,
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL, UNIQUE(tenant_id, document_type, source_type, source_id)
);

CREATE TABLE IF NOT EXISTS employment_contracts (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, employee_id TEXT NOT NULL REFERENCES employees(id),
  contract_type TEXT NOT NULL, starts_on TEXT NOT NULL, ends_on TEXT, salary NUMERIC, weekly_hours NUMERIC,
  schedule_json TEXT NOT NULL DEFAULT '{}', state TEXT NOT NULL DEFAULT 'active', version INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS payroll_runs (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, competence TEXT NOT NULL, run_type TEXT NOT NULL DEFAULT 'monthly',
  state TEXT NOT NULL DEFAULT 'draft', gross_total NUMERIC NOT NULL DEFAULT 0, deductions_total NUMERIC NOT NULL DEFAULT 0,
  net_total NUMERIC NOT NULL DEFAULT 0, version INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
  UNIQUE(tenant_id, competence, run_type)
);
CREATE TABLE IF NOT EXISTS payroll_entries (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, payroll_run_id TEXT NOT NULL REFERENCES payroll_runs(id),
  employee_id TEXT NOT NULL REFERENCES employees(id), gross_amount NUMERIC NOT NULL DEFAULT 0,
  deductions_amount NUMERIC NOT NULL DEFAULT 0, net_amount NUMERIC NOT NULL DEFAULT 0,
  items_json TEXT NOT NULL DEFAULT '[]', state TEXT NOT NULL DEFAULT 'calculated', created_at TEXT NOT NULL,
  UNIQUE(payroll_run_id, employee_id)
);
CREATE TABLE IF NOT EXISTS time_entries (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, employee_id TEXT NOT NULL REFERENCES employees(id),
  occurred_at TEXT NOT NULL, event_type TEXT NOT NULL, origin TEXT NOT NULL, device_id TEXT,
  latitude NUMERIC, longitude NUMERIC, idempotency_key TEXT, state TEXT NOT NULL DEFAULT 'valid',
  created_at TEXT NOT NULL, UNIQUE(tenant_id, idempotency_key)
);

CREATE TABLE IF NOT EXISTS events (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, event_type TEXT NOT NULL, name TEXT NOT NULL,
  starts_at TEXT NOT NULL, ends_at TEXT NOT NULL, location TEXT, capacity INTEGER, state TEXT NOT NULL DEFAULT 'draft',
  budget NUMERIC, payload_json TEXT NOT NULL DEFAULT '{}', version INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS trips (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, event_id TEXT REFERENCES events(id), name TEXT NOT NULL,
  destination TEXT NOT NULL, starts_at TEXT NOT NULL, ends_at TEXT NOT NULL,
  itinerary_json TEXT NOT NULL DEFAULT '[]', vehicles_json TEXT NOT NULL DEFAULT '[]', emergency_json TEXT NOT NULL DEFAULT '{}',
  state TEXT NOT NULL DEFAULT 'draft', created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS notices (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, title TEXT NOT NULL, body TEXT NOT NULL, priority TEXT NOT NULL DEFAULT 'normal',
  audience_json TEXT NOT NULL, channels_json TEXT NOT NULL DEFAULT '["internal"]', scheduled_at TEXT, expires_at TEXT,
  state TEXT NOT NULL DEFAULT 'draft', created_by TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS service_requests (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, protocol TEXT NOT NULL, requester_person_id TEXT REFERENCES people(id),
  request_type TEXT NOT NULL, subject TEXT NOT NULL, description TEXT, priority TEXT NOT NULL DEFAULT 'normal',
  department TEXT, assigned_user_id TEXT, sla_due_at TEXT, state TEXT NOT NULL DEFAULT 'open', version INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL, UNIQUE(tenant_id, protocol)
);
CREATE TABLE IF NOT EXISTS automation_rules (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, name TEXT NOT NULL, trigger_type TEXT NOT NULL,
  trigger_key TEXT NOT NULL, conditions_json TEXT NOT NULL DEFAULT '{}', actions_json TEXT NOT NULL DEFAULT '[]',
  state TEXT NOT NULL DEFAULT 'active', version INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS automation_executions (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, rule_id TEXT NOT NULL REFERENCES automation_rules(id),
  event_id TEXT, state TEXT NOT NULL, dry_run INTEGER NOT NULL DEFAULT 0, input_json TEXT NOT NULL,
  result_json TEXT NOT NULL DEFAULT '{}', error TEXT, started_at TEXT NOT NULL, finished_at TEXT
);
CREATE TABLE IF NOT EXISTS notifications (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, recipient_person_id TEXT REFERENCES people(id),
  channel TEXT NOT NULL, template_key TEXT, subject TEXT, body TEXT NOT NULL, state TEXT NOT NULL DEFAULT 'queued',
  provider_message_id TEXT, scheduled_at TEXT, sent_at TEXT, attempts INTEGER NOT NULL DEFAULT 0,
  idempotency_key TEXT, created_at TEXT NOT NULL, UNIQUE(tenant_id, idempotency_key)
);
CREATE TABLE IF NOT EXISTS library_items (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, inventory_code TEXT NOT NULL, title TEXT NOT NULL,
  authors TEXT, isbn TEXT, category TEXT, item_type TEXT NOT NULL DEFAULT 'book', state TEXT NOT NULL DEFAULT 'available',
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL, UNIQUE(tenant_id, inventory_code)
);
CREATE TABLE IF NOT EXISTS library_loans (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, library_item_id TEXT NOT NULL REFERENCES library_items(id),
  person_id TEXT NOT NULL REFERENCES people(id), loaned_at TEXT NOT NULL, due_at TEXT NOT NULL,
  returned_at TEXT, renewal_count INTEGER NOT NULL DEFAULT 0, fine_amount NUMERIC NOT NULL DEFAULT 0,
  state TEXT NOT NULL DEFAULT 'open', created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS transport_routes (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, code TEXT NOT NULL, name TEXT NOT NULL,
  vehicle TEXT, driver_person_id TEXT REFERENCES people(id), monitor_person_id TEXT REFERENCES people(id),
  stops_json TEXT NOT NULL DEFAULT '[]', state TEXT NOT NULL DEFAULT 'active', created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
  UNIQUE(tenant_id, code)
);
CREATE TABLE IF NOT EXISTS transport_riders (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, route_id TEXT NOT NULL REFERENCES transport_routes(id),
  student_id TEXT NOT NULL REFERENCES students(id), boarding_stop TEXT, dropoff_stop TEXT,
  state TEXT NOT NULL DEFAULT 'active', created_at TEXT NOT NULL, UNIQUE(tenant_id, route_id, student_id)
);
CREATE TABLE IF NOT EXISTS health_records (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, person_id TEXT NOT NULL REFERENCES people(id),
  record_type TEXT NOT NULL, summary TEXT NOT NULL, details_json TEXT NOT NULL DEFAULT '{}',
  sensitivity TEXT NOT NULL DEFAULT 'restricted', valid_from TEXT, valid_until TEXT, state TEXT NOT NULL DEFAULT 'active',
  created_by TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS health_access_log (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, health_record_id TEXT NOT NULL REFERENCES health_records(id),
  actor_user_id TEXT NOT NULL, reason TEXT NOT NULL, accessed_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS documents (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, owner_type TEXT NOT NULL, owner_id TEXT,
  category TEXT NOT NULL, original_filename TEXT NOT NULL, mime_type TEXT NOT NULL, bytes INTEGER NOT NULL,
  sha256 TEXT NOT NULL, storage_key TEXT NOT NULL, antivirus_state TEXT NOT NULL DEFAULT 'not_configured',
  state TEXT NOT NULL DEFAULT 'active', created_by TEXT NOT NULL, created_at TEXT NOT NULL,
  UNIQUE(tenant_id, sha256, category, owner_type, owner_id)
);
CREATE TABLE IF NOT EXISTS integration_connections (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, provider TEXT NOT NULL, name TEXT NOT NULL,
  environment TEXT NOT NULL DEFAULT 'production', capabilities_json TEXT NOT NULL DEFAULT '[]',
  secret_reference TEXT, config_json TEXT NOT NULL DEFAULT '{}', state TEXT NOT NULL DEFAULT 'not_configured',
  last_health_at TEXT, last_health_state TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS integration_runs (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, connection_id TEXT NOT NULL REFERENCES integration_connections(id),
  direction TEXT NOT NULL, capability TEXT NOT NULL, state TEXT NOT NULL, cursor TEXT,
  stats_json TEXT NOT NULL DEFAULT '{}', error TEXT, started_at TEXT NOT NULL, finished_at TEXT
);
CREATE TABLE IF NOT EXISTS government_export_layouts (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, authority TEXT NOT NULL, layout_code TEXT NOT NULL,
  version TEXT NOT NULL, effective_from TEXT NOT NULL, effective_until TEXT,
  schema_json TEXT NOT NULL, state TEXT NOT NULL DEFAULT 'active', created_at TEXT NOT NULL,
  UNIQUE(tenant_id, authority, layout_code, version)
);
CREATE TABLE IF NOT EXISTS government_exports (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, layout_id TEXT NOT NULL REFERENCES government_export_layouts(id),
  reference_period TEXT NOT NULL, state TEXT NOT NULL DEFAULT 'generated', record_count INTEGER NOT NULL DEFAULT 0,
  sha256 TEXT NOT NULL, storage_key TEXT NOT NULL, validation_json TEXT NOT NULL DEFAULT '{}',
  protocol TEXT, created_by TEXT NOT NULL, created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS contract_templates (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, contract_type TEXT NOT NULL, name TEXT NOT NULL,
  state TEXT NOT NULL DEFAULT 'draft', current_version INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS contract_template_versions (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, template_id TEXT NOT NULL REFERENCES contract_templates(id),
  version INTEGER NOT NULL, body_text TEXT NOT NULL, variables_json TEXT NOT NULL DEFAULT '[]',
  rules_json TEXT NOT NULL DEFAULT '{}', sha256 TEXT NOT NULL, state TEXT NOT NULL DEFAULT 'draft',
  created_by TEXT NOT NULL, created_at TEXT NOT NULL, UNIQUE(template_id, version)
);
CREATE TABLE IF NOT EXISTS legal_contracts (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, contract_type TEXT NOT NULL, number TEXT NOT NULL,
  enrollment_id TEXT REFERENCES enrollments(id), financial_contract_id TEXT REFERENCES financial_contracts(id),
  template_version_id TEXT REFERENCES contract_template_versions(id), state TEXT NOT NULL DEFAULT 'draft',
  effective_from TEXT, effective_until TEXT, validation_code TEXT, document_sha256 TEXT, document_storage_key TEXT,
  snapshot_id TEXT, version INTEGER NOT NULL DEFAULT 1, created_by TEXT NOT NULL, updated_by TEXT NOT NULL,
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL, UNIQUE(tenant_id, number)
);
CREATE TABLE IF NOT EXISTS contract_parties (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, contract_id TEXT NOT NULL REFERENCES legal_contracts(id),
  party_type TEXT NOT NULL, person_id TEXT REFERENCES people(id), legal_name TEXT,
  document_number TEXT, role TEXT NOT NULL, signing_required INTEGER NOT NULL DEFAULT 1,
  signing_order INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS contract_events (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, contract_id TEXT NOT NULL REFERENCES legal_contracts(id),
  event_type TEXT NOT NULL, payload_json TEXT NOT NULL DEFAULT '{}', actor_id TEXT, reason TEXT,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS payroll_rules (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, code TEXT NOT NULL, name TEXT NOT NULL,
  direction TEXT NOT NULL, calculation_type TEXT NOT NULL, basis TEXT NOT NULL,
  value NUMERIC NOT NULL, effective_from TEXT NOT NULL, effective_until TEXT,
  priority INTEGER NOT NULL DEFAULT 100, state TEXT NOT NULL DEFAULT 'active', version INTEGER NOT NULL DEFAULT 1,
  metadata_json TEXT NOT NULL DEFAULT '{}', created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
  UNIQUE(tenant_id, code, version)
);
CREATE TABLE IF NOT EXISTS hr_events (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, employee_id TEXT NOT NULL REFERENCES employees(id),
  event_type TEXT NOT NULL, starts_on TEXT NOT NULL, ends_on TEXT, payload_json TEXT NOT NULL DEFAULT '{}',
  state TEXT NOT NULL DEFAULT 'active', created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
"""

RLS_SQL = r"""
ALTER TABLE users ENABLE ROW LEVEL SECURITY;
ALTER TABLE users FORCE ROW LEVEL SECURITY;
CREATE POLICY pige360_tenant_users ON users USING (tenant_id = current_setting('app.tenant_id', true)) WITH CHECK (tenant_id = current_setting('app.tenant_id', true));
ALTER TABLE refresh_tokens ENABLE ROW LEVEL SECURITY;
ALTER TABLE refresh_tokens FORCE ROW LEVEL SECURITY;
CREATE POLICY pige360_tenant_refresh_tokens ON refresh_tokens USING (tenant_id = current_setting('app.tenant_id', true)) WITH CHECK (tenant_id = current_setting('app.tenant_id', true));
ALTER TABLE audit_log ENABLE ROW LEVEL SECURITY;
ALTER TABLE audit_log FORCE ROW LEVEL SECURITY;
CREATE POLICY pige360_tenant_audit_log ON audit_log USING (tenant_id = current_setting('app.tenant_id', true)) WITH CHECK (tenant_id = current_setting('app.tenant_id', true));
ALTER TABLE outbox_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE outbox_events FORCE ROW LEVEL SECURITY;
CREATE POLICY pige360_tenant_outbox_events ON outbox_events USING (tenant_id = current_setting('app.tenant_id', true)) WITH CHECK (tenant_id = current_setting('app.tenant_id', true));
ALTER TABLE brand_kits ENABLE ROW LEVEL SECURITY;
ALTER TABLE brand_kits FORCE ROW LEVEL SECURITY;
CREATE POLICY pige360_tenant_brand_kits ON brand_kits USING (tenant_id = current_setting('app.tenant_id', true)) WITH CHECK (tenant_id = current_setting('app.tenant_id', true));
ALTER TABLE brand_versions ENABLE ROW LEVEL SECURITY;
ALTER TABLE brand_versions FORCE ROW LEVEL SECURITY;
CREATE POLICY pige360_tenant_brand_versions ON brand_versions USING (tenant_id = current_setting('app.tenant_id', true)) WITH CHECK (tenant_id = current_setting('app.tenant_id', true));
ALTER TABLE brand_assets ENABLE ROW LEVEL SECURITY;
ALTER TABLE brand_assets FORCE ROW LEVEL SECURITY;
CREATE POLICY pige360_tenant_brand_assets ON brand_assets USING (tenant_id = current_setting('app.tenant_id', true)) WITH CHECK (tenant_id = current_setting('app.tenant_id', true));
ALTER TABLE tenant_app_manifests ENABLE ROW LEVEL SECURITY;
ALTER TABLE tenant_app_manifests FORCE ROW LEVEL SECURITY;
CREATE POLICY pige360_tenant_tenant_app_manifests ON tenant_app_manifests USING (tenant_id = current_setting('app.tenant_id', true)) WITH CHECK (tenant_id = current_setting('app.tenant_id', true));
ALTER TABLE app_build_requests ENABLE ROW LEVEL SECURITY;
ALTER TABLE app_build_requests FORCE ROW LEVEL SECURITY;
CREATE POLICY pige360_tenant_app_build_requests ON app_build_requests USING (tenant_id = current_setting('app.tenant_id', true)) WITH CHECK (tenant_id = current_setting('app.tenant_id', true));
ALTER TABLE teaching_plans ENABLE ROW LEVEL SECURITY;
ALTER TABLE teaching_plans FORCE ROW LEVEL SECURITY;
CREATE POLICY pige360_tenant_teaching_plans ON teaching_plans USING (tenant_id = current_setting('app.tenant_id', true)) WITH CHECK (tenant_id = current_setting('app.tenant_id', true));
ALTER TABLE teaching_plan_versions ENABLE ROW LEVEL SECURITY;
ALTER TABLE teaching_plan_versions FORCE ROW LEVEL SECURITY;
CREATE POLICY pige360_tenant_teaching_plan_versions ON teaching_plan_versions USING (tenant_id = current_setting('app.tenant_id', true)) WITH CHECK (tenant_id = current_setting('app.tenant_id', true));
ALTER TABLE teaching_plan_approvals ENABLE ROW LEVEL SECURITY;
ALTER TABLE teaching_plan_approvals FORCE ROW LEVEL SECURITY;
CREATE POLICY pige360_tenant_teaching_plan_approvals ON teaching_plan_approvals USING (tenant_id = current_setting('app.tenant_id', true)) WITH CHECK (tenant_id = current_setting('app.tenant_id', true));
ALTER TABLE lesson_plans ENABLE ROW LEVEL SECURITY;
ALTER TABLE lesson_plans FORCE ROW LEVEL SECURITY;
CREATE POLICY pige360_tenant_lesson_plans ON lesson_plans USING (tenant_id = current_setting('app.tenant_id', true)) WITH CHECK (tenant_id = current_setting('app.tenant_id', true));
ALTER TABLE lesson_plan_versions ENABLE ROW LEVEL SECURITY;
ALTER TABLE lesson_plan_versions FORCE ROW LEVEL SECURITY;
CREATE POLICY pige360_tenant_lesson_plan_versions ON lesson_plan_versions USING (tenant_id = current_setting('app.tenant_id', true)) WITH CHECK (tenant_id = current_setting('app.tenant_id', true));
ALTER TABLE lesson_plan_execution_records ENABLE ROW LEVEL SECURITY;
ALTER TABLE lesson_plan_execution_records FORCE ROW LEVEL SECURITY;
CREATE POLICY pige360_tenant_lesson_plan_execution_records ON lesson_plan_execution_records USING (tenant_id = current_setting('app.tenant_id', true)) WITH CHECK (tenant_id = current_setting('app.tenant_id', true));
ALTER TABLE attendance_policies ENABLE ROW LEVEL SECURITY;
ALTER TABLE attendance_policies FORCE ROW LEVEL SECURITY;
CREATE POLICY pige360_tenant_attendance_policies ON attendance_policies USING (tenant_id = current_setting('app.tenant_id', true)) WITH CHECK (tenant_id = current_setting('app.tenant_id', true));
ALTER TABLE attendance_policy_versions ENABLE ROW LEVEL SECURITY;
ALTER TABLE attendance_policy_versions FORCE ROW LEVEL SECURITY;
CREATE POLICY pige360_tenant_attendance_policy_versions ON attendance_policy_versions USING (tenant_id = current_setting('app.tenant_id', true)) WITH CHECK (tenant_id = current_setting('app.tenant_id', true));
ALTER TABLE class_sessions ENABLE ROW LEVEL SECURITY;
ALTER TABLE class_sessions FORCE ROW LEVEL SECURITY;
CREATE POLICY pige360_tenant_class_sessions ON class_sessions USING (tenant_id = current_setting('app.tenant_id', true)) WITH CHECK (tenant_id = current_setting('app.tenant_id', true));
ALTER TABLE attendance_calls ENABLE ROW LEVEL SECURITY;
ALTER TABLE attendance_calls FORCE ROW LEVEL SECURITY;
CREATE POLICY pige360_tenant_attendance_calls ON attendance_calls USING (tenant_id = current_setting('app.tenant_id', true)) WITH CHECK (tenant_id = current_setting('app.tenant_id', true));
ALTER TABLE attendance_call_versions ENABLE ROW LEVEL SECURITY;
ALTER TABLE attendance_call_versions FORCE ROW LEVEL SECURITY;
CREATE POLICY pige360_tenant_attendance_call_versions ON attendance_call_versions USING (tenant_id = current_setting('app.tenant_id', true)) WITH CHECK (tenant_id = current_setting('app.tenant_id', true));
ALTER TABLE attendance_records ENABLE ROW LEVEL SECURITY;
ALTER TABLE attendance_records FORCE ROW LEVEL SECURITY;
CREATE POLICY pige360_tenant_attendance_records ON attendance_records USING (tenant_id = current_setting('app.tenant_id', true)) WITH CHECK (tenant_id = current_setting('app.tenant_id', true));
ALTER TABLE attendance_record_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE attendance_record_events FORCE ROW LEVEL SECURITY;
CREATE POLICY pige360_tenant_attendance_record_events ON attendance_record_events USING (tenant_id = current_setting('app.tenant_id', true)) WITH CHECK (tenant_id = current_setting('app.tenant_id', true));
ALTER TABLE attendance_justifications ENABLE ROW LEVEL SECURITY;
ALTER TABLE attendance_justifications FORCE ROW LEVEL SECURITY;
CREATE POLICY pige360_tenant_attendance_justifications ON attendance_justifications USING (tenant_id = current_setting('app.tenant_id', true)) WITH CHECK (tenant_id = current_setting('app.tenant_id', true));
ALTER TABLE attendance_corrections ENABLE ROW LEVEL SECURITY;
ALTER TABLE attendance_corrections FORCE ROW LEVEL SECURITY;
CREATE POLICY pige360_tenant_attendance_corrections ON attendance_corrections USING (tenant_id = current_setting('app.tenant_id', true)) WITH CHECK (tenant_id = current_setting('app.tenant_id', true));
ALTER TABLE contract_snapshots ENABLE ROW LEVEL SECURITY;
ALTER TABLE contract_snapshots FORCE ROW LEVEL SECURITY;
CREATE POLICY pige360_tenant_contract_snapshots ON contract_snapshots USING (tenant_id = current_setting('app.tenant_id', true)) WITH CHECK (tenant_id = current_setting('app.tenant_id', true));
ALTER TABLE signature_envelopes ENABLE ROW LEVEL SECURITY;
ALTER TABLE signature_envelopes FORCE ROW LEVEL SECURITY;
CREATE POLICY pige360_tenant_signature_envelopes ON signature_envelopes USING (tenant_id = current_setting('app.tenant_id', true)) WITH CHECK (tenant_id = current_setting('app.tenant_id', true));
ALTER TABLE tenant_app_entitlements ENABLE ROW LEVEL SECURITY;
ALTER TABLE tenant_app_entitlements FORCE ROW LEVEL SECURITY;
CREATE POLICY pige360_tenant_tenant_app_entitlements ON tenant_app_entitlements USING (tenant_id = current_setting('app.tenant_id', true)) WITH CHECK (tenant_id = current_setting('app.tenant_id', true));
ALTER TABLE app_build_jobs ENABLE ROW LEVEL SECURITY;
ALTER TABLE app_build_jobs FORCE ROW LEVEL SECURITY;
CREATE POLICY pige360_tenant_app_build_jobs ON app_build_jobs USING (tenant_id = current_setting('app.tenant_id', true)) WITH CHECK (tenant_id = current_setting('app.tenant_id', true));
ALTER TABLE app_build_artifacts ENABLE ROW LEVEL SECURITY;
ALTER TABLE app_build_artifacts FORCE ROW LEVEL SECURITY;
CREATE POLICY pige360_tenant_app_build_artifacts ON app_build_artifacts USING (tenant_id = current_setting('app.tenant_id', true)) WITH CHECK (tenant_id = current_setting('app.tenant_id', true));
ALTER TABLE app_releases ENABLE ROW LEVEL SECURITY;
ALTER TABLE app_releases FORCE ROW LEVEL SECURITY;
CREATE POLICY pige360_tenant_app_releases ON app_releases USING (tenant_id = current_setting('app.tenant_id', true)) WITH CHECK (tenant_id = current_setting('app.tenant_id', true));
ALTER TABLE app_release_artifacts ENABLE ROW LEVEL SECURITY;
ALTER TABLE app_release_artifacts FORCE ROW LEVEL SECURITY;
CREATE POLICY pige360_tenant_app_release_artifacts ON app_release_artifacts USING (tenant_id = current_setting('app.tenant_id', true)) WITH CHECK (tenant_id = current_setting('app.tenant_id', true));
ALTER TABLE app_download_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE app_download_events FORCE ROW LEVEL SECURITY;
CREATE POLICY pige360_tenant_app_download_events ON app_download_events USING (tenant_id = current_setting('app.tenant_id', true)) WITH CHECK (tenant_id = current_setting('app.tenant_id', true));
ALTER TABLE institutions ENABLE ROW LEVEL SECURITY;
ALTER TABLE institutions FORCE ROW LEVEL SECURITY;
CREATE POLICY pige360_tenant_institutions ON institutions USING (tenant_id = current_setting('app.tenant_id', true)) WITH CHECK (tenant_id = current_setting('app.tenant_id', true));
ALTER TABLE units ENABLE ROW LEVEL SECURITY;
ALTER TABLE units FORCE ROW LEVEL SECURITY;
CREATE POLICY pige360_tenant_units ON units USING (tenant_id = current_setting('app.tenant_id', true)) WITH CHECK (tenant_id = current_setting('app.tenant_id', true));
ALTER TABLE academic_years ENABLE ROW LEVEL SECURITY;
ALTER TABLE academic_years FORCE ROW LEVEL SECURITY;
CREATE POLICY pige360_tenant_academic_years ON academic_years USING (tenant_id = current_setting('app.tenant_id', true)) WITH CHECK (tenant_id = current_setting('app.tenant_id', true));
ALTER TABLE programs ENABLE ROW LEVEL SECURITY;
ALTER TABLE programs FORCE ROW LEVEL SECURITY;
CREATE POLICY pige360_tenant_programs ON programs USING (tenant_id = current_setting('app.tenant_id', true)) WITH CHECK (tenant_id = current_setting('app.tenant_id', true));
ALTER TABLE curricula ENABLE ROW LEVEL SECURITY;
ALTER TABLE curricula FORCE ROW LEVEL SECURITY;
CREATE POLICY pige360_tenant_curricula ON curricula USING (tenant_id = current_setting('app.tenant_id', true)) WITH CHECK (tenant_id = current_setting('app.tenant_id', true));
ALTER TABLE curriculum_components ENABLE ROW LEVEL SECURITY;
ALTER TABLE curriculum_components FORCE ROW LEVEL SECURITY;
CREATE POLICY pige360_tenant_curriculum_components ON curriculum_components USING (tenant_id = current_setting('app.tenant_id', true)) WITH CHECK (tenant_id = current_setting('app.tenant_id', true));
ALTER TABLE class_groups ENABLE ROW LEVEL SECURITY;
ALTER TABLE class_groups FORCE ROW LEVEL SECURITY;
CREATE POLICY pige360_tenant_class_groups ON class_groups USING (tenant_id = current_setting('app.tenant_id', true)) WITH CHECK (tenant_id = current_setting('app.tenant_id', true));
ALTER TABLE people ENABLE ROW LEVEL SECURITY;
ALTER TABLE people FORCE ROW LEVEL SECURITY;
CREATE POLICY pige360_tenant_people ON people USING (tenant_id = current_setting('app.tenant_id', true)) WITH CHECK (tenant_id = current_setting('app.tenant_id', true));
ALTER TABLE students ENABLE ROW LEVEL SECURITY;
ALTER TABLE students FORCE ROW LEVEL SECURITY;
CREATE POLICY pige360_tenant_students ON students USING (tenant_id = current_setting('app.tenant_id', true)) WITH CHECK (tenant_id = current_setting('app.tenant_id', true));
ALTER TABLE guardians ENABLE ROW LEVEL SECURITY;
ALTER TABLE guardians FORCE ROW LEVEL SECURITY;
CREATE POLICY pige360_tenant_guardians ON guardians USING (tenant_id = current_setting('app.tenant_id', true)) WITH CHECK (tenant_id = current_setting('app.tenant_id', true));
ALTER TABLE guardian_students ENABLE ROW LEVEL SECURITY;
ALTER TABLE guardian_students FORCE ROW LEVEL SECURITY;
CREATE POLICY pige360_tenant_guardian_students ON guardian_students USING (tenant_id = current_setting('app.tenant_id', true)) WITH CHECK (tenant_id = current_setting('app.tenant_id', true));
ALTER TABLE employees ENABLE ROW LEVEL SECURITY;
ALTER TABLE employees FORCE ROW LEVEL SECURITY;
CREATE POLICY pige360_tenant_employees ON employees USING (tenant_id = current_setting('app.tenant_id', true)) WITH CHECK (tenant_id = current_setting('app.tenant_id', true));
ALTER TABLE teacher_assignments ENABLE ROW LEVEL SECURITY;
ALTER TABLE teacher_assignments FORCE ROW LEVEL SECURITY;
CREATE POLICY pige360_tenant_teacher_assignments ON teacher_assignments USING (tenant_id = current_setting('app.tenant_id', true)) WITH CHECK (tenant_id = current_setting('app.tenant_id', true));
ALTER TABLE admission_candidates ENABLE ROW LEVEL SECURITY;
ALTER TABLE admission_candidates FORCE ROW LEVEL SECURITY;
CREATE POLICY pige360_tenant_admission_candidates ON admission_candidates USING (tenant_id = current_setting('app.tenant_id', true)) WITH CHECK (tenant_id = current_setting('app.tenant_id', true));
ALTER TABLE enrollments ENABLE ROW LEVEL SECURITY;
ALTER TABLE enrollments FORCE ROW LEVEL SECURITY;
CREATE POLICY pige360_tenant_enrollments ON enrollments USING (tenant_id = current_setting('app.tenant_id', true)) WITH CHECK (tenant_id = current_setting('app.tenant_id', true));
ALTER TABLE financial_contracts ENABLE ROW LEVEL SECURITY;
ALTER TABLE financial_contracts FORCE ROW LEVEL SECURITY;
CREATE POLICY pige360_tenant_financial_contracts ON financial_contracts USING (tenant_id = current_setting('app.tenant_id', true)) WITH CHECK (tenant_id = current_setting('app.tenant_id', true));
ALTER TABLE installments ENABLE ROW LEVEL SECURITY;
ALTER TABLE installments FORCE ROW LEVEL SECURITY;
CREATE POLICY pige360_tenant_installments ON installments USING (tenant_id = current_setting('app.tenant_id', true)) WITH CHECK (tenant_id = current_setting('app.tenant_id', true));
ALTER TABLE payments ENABLE ROW LEVEL SECURITY;
ALTER TABLE payments FORCE ROW LEVEL SECURITY;
CREATE POLICY pige360_tenant_payments ON payments USING (tenant_id = current_setting('app.tenant_id', true)) WITH CHECK (tenant_id = current_setting('app.tenant_id', true));
ALTER TABLE payment_allocations ENABLE ROW LEVEL SECURITY;
ALTER TABLE payment_allocations FORCE ROW LEVEL SECURITY;
CREATE POLICY pige360_tenant_payment_allocations ON payment_allocations USING (tenant_id = current_setting('app.tenant_id', true)) WITH CHECK (tenant_id = current_setting('app.tenant_id', true));
ALTER TABLE ledger_entries ENABLE ROW LEVEL SECURITY;
ALTER TABLE ledger_entries FORCE ROW LEVEL SECURITY;
CREATE POLICY pige360_tenant_ledger_entries ON ledger_entries USING (tenant_id = current_setting('app.tenant_id', true)) WITH CHECK (tenant_id = current_setting('app.tenant_id', true));
ALTER TABLE bank_accounts ENABLE ROW LEVEL SECURITY;
ALTER TABLE bank_accounts FORCE ROW LEVEL SECURITY;
CREATE POLICY pige360_tenant_bank_accounts ON bank_accounts USING (tenant_id = current_setting('app.tenant_id', true)) WITH CHECK (tenant_id = current_setting('app.tenant_id', true));
ALTER TABLE pix_charges ENABLE ROW LEVEL SECURITY;
ALTER TABLE pix_charges FORCE ROW LEVEL SECURITY;
CREATE POLICY pige360_tenant_pix_charges ON pix_charges USING (tenant_id = current_setting('app.tenant_id', true)) WITH CHECK (tenant_id = current_setting('app.tenant_id', true));
ALTER TABLE bank_imports ENABLE ROW LEVEL SECURITY;
ALTER TABLE bank_imports FORCE ROW LEVEL SECURITY;
CREATE POLICY pige360_tenant_bank_imports ON bank_imports USING (tenant_id = current_setting('app.tenant_id', true)) WITH CHECK (tenant_id = current_setting('app.tenant_id', true));
ALTER TABLE bank_transactions ENABLE ROW LEVEL SECURITY;
ALTER TABLE bank_transactions FORCE ROW LEVEL SECURITY;
CREATE POLICY pige360_tenant_bank_transactions ON bank_transactions USING (tenant_id = current_setting('app.tenant_id', true)) WITH CHECK (tenant_id = current_setting('app.tenant_id', true));
ALTER TABLE services ENABLE ROW LEVEL SECURITY;
ALTER TABLE services FORCE ROW LEVEL SECURITY;
CREATE POLICY pige360_tenant_services ON services USING (tenant_id = current_setting('app.tenant_id', true)) WITH CHECK (tenant_id = current_setting('app.tenant_id', true));
ALTER TABLE service_orders ENABLE ROW LEVEL SECURITY;
ALTER TABLE service_orders FORCE ROW LEVEL SECURITY;
CREATE POLICY pige360_tenant_service_orders ON service_orders USING (tenant_id = current_setting('app.tenant_id', true)) WITH CHECK (tenant_id = current_setting('app.tenant_id', true));
ALTER TABLE service_order_items ENABLE ROW LEVEL SECURITY;
ALTER TABLE service_order_items FORCE ROW LEVEL SECURITY;
CREATE POLICY pige360_tenant_service_order_items ON service_order_items USING (tenant_id = current_setting('app.tenant_id', true)) WITH CHECK (tenant_id = current_setting('app.tenant_id', true));
ALTER TABLE products ENABLE ROW LEVEL SECURITY;
ALTER TABLE products FORCE ROW LEVEL SECURITY;
CREATE POLICY pige360_tenant_products ON products USING (tenant_id = current_setting('app.tenant_id', true)) WITH CHECK (tenant_id = current_setting('app.tenant_id', true));
ALTER TABLE stock_balances ENABLE ROW LEVEL SECURITY;
ALTER TABLE stock_balances FORCE ROW LEVEL SECURITY;
CREATE POLICY pige360_tenant_stock_balances ON stock_balances USING (tenant_id = current_setting('app.tenant_id', true)) WITH CHECK (tenant_id = current_setting('app.tenant_id', true));
ALTER TABLE stock_movements ENABLE ROW LEVEL SECURITY;
ALTER TABLE stock_movements FORCE ROW LEVEL SECURITY;
CREATE POLICY pige360_tenant_stock_movements ON stock_movements USING (tenant_id = current_setting('app.tenant_id', true)) WITH CHECK (tenant_id = current_setting('app.tenant_id', true));
ALTER TABLE cash_sessions ENABLE ROW LEVEL SECURITY;
ALTER TABLE cash_sessions FORCE ROW LEVEL SECURITY;
CREATE POLICY pige360_tenant_cash_sessions ON cash_sessions USING (tenant_id = current_setting('app.tenant_id', true)) WITH CHECK (tenant_id = current_setting('app.tenant_id', true));
ALTER TABLE sales ENABLE ROW LEVEL SECURITY;
ALTER TABLE sales FORCE ROW LEVEL SECURITY;
CREATE POLICY pige360_tenant_sales ON sales USING (tenant_id = current_setting('app.tenant_id', true)) WITH CHECK (tenant_id = current_setting('app.tenant_id', true));
ALTER TABLE sale_items ENABLE ROW LEVEL SECURITY;
ALTER TABLE sale_items FORCE ROW LEVEL SECURITY;
CREATE POLICY pige360_tenant_sale_items ON sale_items USING (tenant_id = current_setting('app.tenant_id', true)) WITH CHECK (tenant_id = current_setting('app.tenant_id', true));
ALTER TABLE sale_payments ENABLE ROW LEVEL SECURITY;
ALTER TABLE sale_payments FORCE ROW LEVEL SECURITY;
CREATE POLICY pige360_tenant_sale_payments ON sale_payments USING (tenant_id = current_setting('app.tenant_id', true)) WITH CHECK (tenant_id = current_setting('app.tenant_id', true));
ALTER TABLE suppliers ENABLE ROW LEVEL SECURITY;
ALTER TABLE suppliers FORCE ROW LEVEL SECURITY;
CREATE POLICY pige360_tenant_suppliers ON suppliers USING (tenant_id = current_setting('app.tenant_id', true)) WITH CHECK (tenant_id = current_setting('app.tenant_id', true));
ALTER TABLE purchase_orders ENABLE ROW LEVEL SECURITY;
ALTER TABLE purchase_orders FORCE ROW LEVEL SECURITY;
CREATE POLICY pige360_tenant_purchase_orders ON purchase_orders USING (tenant_id = current_setting('app.tenant_id', true)) WITH CHECK (tenant_id = current_setting('app.tenant_id', true));
ALTER TABLE purchase_order_items ENABLE ROW LEVEL SECURITY;
ALTER TABLE purchase_order_items FORCE ROW LEVEL SECURITY;
CREATE POLICY pige360_tenant_purchase_order_items ON purchase_order_items USING (tenant_id = current_setting('app.tenant_id', true)) WITH CHECK (tenant_id = current_setting('app.tenant_id', true));
ALTER TABLE assets ENABLE ROW LEVEL SECURITY;
ALTER TABLE assets FORCE ROW LEVEL SECURITY;
CREATE POLICY pige360_tenant_assets ON assets USING (tenant_id = current_setting('app.tenant_id', true)) WITH CHECK (tenant_id = current_setting('app.tenant_id', true));
ALTER TABLE fiscal_profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE fiscal_profiles FORCE ROW LEVEL SECURITY;
CREATE POLICY pige360_tenant_fiscal_profiles ON fiscal_profiles USING (tenant_id = current_setting('app.tenant_id', true)) WITH CHECK (tenant_id = current_setting('app.tenant_id', true));
ALTER TABLE fiscal_rules ENABLE ROW LEVEL SECURITY;
ALTER TABLE fiscal_rules FORCE ROW LEVEL SECURITY;
CREATE POLICY pige360_tenant_fiscal_rules ON fiscal_rules USING (tenant_id = current_setting('app.tenant_id', true)) WITH CHECK (tenant_id = current_setting('app.tenant_id', true));
ALTER TABLE fiscal_documents ENABLE ROW LEVEL SECURITY;
ALTER TABLE fiscal_documents FORCE ROW LEVEL SECURITY;
CREATE POLICY pige360_tenant_fiscal_documents ON fiscal_documents USING (tenant_id = current_setting('app.tenant_id', true)) WITH CHECK (tenant_id = current_setting('app.tenant_id', true));
ALTER TABLE employment_contracts ENABLE ROW LEVEL SECURITY;
ALTER TABLE employment_contracts FORCE ROW LEVEL SECURITY;
CREATE POLICY pige360_tenant_employment_contracts ON employment_contracts USING (tenant_id = current_setting('app.tenant_id', true)) WITH CHECK (tenant_id = current_setting('app.tenant_id', true));
ALTER TABLE payroll_runs ENABLE ROW LEVEL SECURITY;
ALTER TABLE payroll_runs FORCE ROW LEVEL SECURITY;
CREATE POLICY pige360_tenant_payroll_runs ON payroll_runs USING (tenant_id = current_setting('app.tenant_id', true)) WITH CHECK (tenant_id = current_setting('app.tenant_id', true));
ALTER TABLE payroll_entries ENABLE ROW LEVEL SECURITY;
ALTER TABLE payroll_entries FORCE ROW LEVEL SECURITY;
CREATE POLICY pige360_tenant_payroll_entries ON payroll_entries USING (tenant_id = current_setting('app.tenant_id', true)) WITH CHECK (tenant_id = current_setting('app.tenant_id', true));
ALTER TABLE time_entries ENABLE ROW LEVEL SECURITY;
ALTER TABLE time_entries FORCE ROW LEVEL SECURITY;
CREATE POLICY pige360_tenant_time_entries ON time_entries USING (tenant_id = current_setting('app.tenant_id', true)) WITH CHECK (tenant_id = current_setting('app.tenant_id', true));
ALTER TABLE events ENABLE ROW LEVEL SECURITY;
ALTER TABLE events FORCE ROW LEVEL SECURITY;
CREATE POLICY pige360_tenant_events ON events USING (tenant_id = current_setting('app.tenant_id', true)) WITH CHECK (tenant_id = current_setting('app.tenant_id', true));
ALTER TABLE trips ENABLE ROW LEVEL SECURITY;
ALTER TABLE trips FORCE ROW LEVEL SECURITY;
CREATE POLICY pige360_tenant_trips ON trips USING (tenant_id = current_setting('app.tenant_id', true)) WITH CHECK (tenant_id = current_setting('app.tenant_id', true));
ALTER TABLE notices ENABLE ROW LEVEL SECURITY;
ALTER TABLE notices FORCE ROW LEVEL SECURITY;
CREATE POLICY pige360_tenant_notices ON notices USING (tenant_id = current_setting('app.tenant_id', true)) WITH CHECK (tenant_id = current_setting('app.tenant_id', true));
ALTER TABLE service_requests ENABLE ROW LEVEL SECURITY;
ALTER TABLE service_requests FORCE ROW LEVEL SECURITY;
CREATE POLICY pige360_tenant_service_requests ON service_requests USING (tenant_id = current_setting('app.tenant_id', true)) WITH CHECK (tenant_id = current_setting('app.tenant_id', true));
ALTER TABLE automation_rules ENABLE ROW LEVEL SECURITY;
ALTER TABLE automation_rules FORCE ROW LEVEL SECURITY;
CREATE POLICY pige360_tenant_automation_rules ON automation_rules USING (tenant_id = current_setting('app.tenant_id', true)) WITH CHECK (tenant_id = current_setting('app.tenant_id', true));
ALTER TABLE automation_executions ENABLE ROW LEVEL SECURITY;
ALTER TABLE automation_executions FORCE ROW LEVEL SECURITY;
CREATE POLICY pige360_tenant_automation_executions ON automation_executions USING (tenant_id = current_setting('app.tenant_id', true)) WITH CHECK (tenant_id = current_setting('app.tenant_id', true));
ALTER TABLE notifications ENABLE ROW LEVEL SECURITY;
ALTER TABLE notifications FORCE ROW LEVEL SECURITY;
CREATE POLICY pige360_tenant_notifications ON notifications USING (tenant_id = current_setting('app.tenant_id', true)) WITH CHECK (tenant_id = current_setting('app.tenant_id', true));
ALTER TABLE library_items ENABLE ROW LEVEL SECURITY;
ALTER TABLE library_items FORCE ROW LEVEL SECURITY;
CREATE POLICY pige360_tenant_library_items ON library_items USING (tenant_id = current_setting('app.tenant_id', true)) WITH CHECK (tenant_id = current_setting('app.tenant_id', true));
ALTER TABLE library_loans ENABLE ROW LEVEL SECURITY;
ALTER TABLE library_loans FORCE ROW LEVEL SECURITY;
CREATE POLICY pige360_tenant_library_loans ON library_loans USING (tenant_id = current_setting('app.tenant_id', true)) WITH CHECK (tenant_id = current_setting('app.tenant_id', true));
ALTER TABLE transport_routes ENABLE ROW LEVEL SECURITY;
ALTER TABLE transport_routes FORCE ROW LEVEL SECURITY;
CREATE POLICY pige360_tenant_transport_routes ON transport_routes USING (tenant_id = current_setting('app.tenant_id', true)) WITH CHECK (tenant_id = current_setting('app.tenant_id', true));
ALTER TABLE transport_riders ENABLE ROW LEVEL SECURITY;
ALTER TABLE transport_riders FORCE ROW LEVEL SECURITY;
CREATE POLICY pige360_tenant_transport_riders ON transport_riders USING (tenant_id = current_setting('app.tenant_id', true)) WITH CHECK (tenant_id = current_setting('app.tenant_id', true));
ALTER TABLE health_records ENABLE ROW LEVEL SECURITY;
ALTER TABLE health_records FORCE ROW LEVEL SECURITY;
CREATE POLICY pige360_tenant_health_records ON health_records USING (tenant_id = current_setting('app.tenant_id', true)) WITH CHECK (tenant_id = current_setting('app.tenant_id', true));
ALTER TABLE health_access_log ENABLE ROW LEVEL SECURITY;
ALTER TABLE health_access_log FORCE ROW LEVEL SECURITY;
CREATE POLICY pige360_tenant_health_access_log ON health_access_log USING (tenant_id = current_setting('app.tenant_id', true)) WITH CHECK (tenant_id = current_setting('app.tenant_id', true));
ALTER TABLE documents ENABLE ROW LEVEL SECURITY;
ALTER TABLE documents FORCE ROW LEVEL SECURITY;
CREATE POLICY pige360_tenant_documents ON documents USING (tenant_id = current_setting('app.tenant_id', true)) WITH CHECK (tenant_id = current_setting('app.tenant_id', true));
ALTER TABLE integration_connections ENABLE ROW LEVEL SECURITY;
ALTER TABLE integration_connections FORCE ROW LEVEL SECURITY;
CREATE POLICY pige360_tenant_integration_connections ON integration_connections USING (tenant_id = current_setting('app.tenant_id', true)) WITH CHECK (tenant_id = current_setting('app.tenant_id', true));
ALTER TABLE integration_runs ENABLE ROW LEVEL SECURITY;
ALTER TABLE integration_runs FORCE ROW LEVEL SECURITY;
CREATE POLICY pige360_tenant_integration_runs ON integration_runs USING (tenant_id = current_setting('app.tenant_id', true)) WITH CHECK (tenant_id = current_setting('app.tenant_id', true));
ALTER TABLE government_export_layouts ENABLE ROW LEVEL SECURITY;
ALTER TABLE government_export_layouts FORCE ROW LEVEL SECURITY;
CREATE POLICY pige360_tenant_government_export_layouts ON government_export_layouts USING (tenant_id = current_setting('app.tenant_id', true)) WITH CHECK (tenant_id = current_setting('app.tenant_id', true));
ALTER TABLE government_exports ENABLE ROW LEVEL SECURITY;
ALTER TABLE government_exports FORCE ROW LEVEL SECURITY;
CREATE POLICY pige360_tenant_government_exports ON government_exports USING (tenant_id = current_setting('app.tenant_id', true)) WITH CHECK (tenant_id = current_setting('app.tenant_id', true));
ALTER TABLE contract_templates ENABLE ROW LEVEL SECURITY;
ALTER TABLE contract_templates FORCE ROW LEVEL SECURITY;
CREATE POLICY pige360_tenant_contract_templates ON contract_templates USING (tenant_id = current_setting('app.tenant_id', true)) WITH CHECK (tenant_id = current_setting('app.tenant_id', true));
ALTER TABLE contract_template_versions ENABLE ROW LEVEL SECURITY;
ALTER TABLE contract_template_versions FORCE ROW LEVEL SECURITY;
CREATE POLICY pige360_tenant_contract_template_versions ON contract_template_versions USING (tenant_id = current_setting('app.tenant_id', true)) WITH CHECK (tenant_id = current_setting('app.tenant_id', true));
ALTER TABLE legal_contracts ENABLE ROW LEVEL SECURITY;
ALTER TABLE legal_contracts FORCE ROW LEVEL SECURITY;
CREATE POLICY pige360_tenant_legal_contracts ON legal_contracts USING (tenant_id = current_setting('app.tenant_id', true)) WITH CHECK (tenant_id = current_setting('app.tenant_id', true));
ALTER TABLE contract_parties ENABLE ROW LEVEL SECURITY;
ALTER TABLE contract_parties FORCE ROW LEVEL SECURITY;
CREATE POLICY pige360_tenant_contract_parties ON contract_parties USING (tenant_id = current_setting('app.tenant_id', true)) WITH CHECK (tenant_id = current_setting('app.tenant_id', true));
ALTER TABLE contract_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE contract_events FORCE ROW LEVEL SECURITY;
CREATE POLICY pige360_tenant_contract_events ON contract_events USING (tenant_id = current_setting('app.tenant_id', true)) WITH CHECK (tenant_id = current_setting('app.tenant_id', true));
ALTER TABLE payroll_rules ENABLE ROW LEVEL SECURITY;
ALTER TABLE payroll_rules FORCE ROW LEVEL SECURITY;
CREATE POLICY pige360_tenant_payroll_rules ON payroll_rules USING (tenant_id = current_setting('app.tenant_id', true)) WITH CHECK (tenant_id = current_setting('app.tenant_id', true));
ALTER TABLE hr_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE hr_events FORCE ROW LEVEL SECURITY;
CREATE POLICY pige360_tenant_hr_events ON hr_events USING (tenant_id = current_setting('app.tenant_id', true)) WITH CHECK (tenant_id = current_setting('app.tenant_id', true));
"""


def upgrade() -> None:
    op.execute(SQL)
    op.execute(RLS_SQL)


def downgrade() -> None:
    raise RuntimeError("Downgrade destrutivo do Tenant Plane não é suportado; use restore validado.")
