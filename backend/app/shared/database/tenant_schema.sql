PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS tenant_metadata (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    person_id TEXT,
    email TEXT NOT NULL COLLATE NOCASE,
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
    family_id TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    revoked_at TEXT,
    replaced_by TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS auth_login_attempts (
    identifier_hash TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    failed_attempts INTEGER NOT NULL CHECK(failed_attempts >= 0),
    window_started_at TEXT NOT NULL,
    locked_until TEXT,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_tenant_auth_login_attempts_updated ON auth_login_attempts(updated_at);

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
    attempts INTEGER NOT NULL DEFAULT 0,
    last_error TEXT,
    next_attempt_at TEXT
);

CREATE TABLE IF NOT EXISTS inbox_events (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    event_id TEXT NOT NULL,
    consumer TEXT NOT NULL,
    event_type TEXT NOT NULL,
    state TEXT NOT NULL DEFAULT 'processing',
    attempts INTEGER NOT NULL DEFAULT 1,
    last_error TEXT,
    result_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    processed_at TEXT,
    UNIQUE(tenant_id, event_id, consumer)
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
CREATE TABLE IF NOT EXISTS signature_otp_challenges (
    id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, envelope_id TEXT NOT NULL REFERENCES signature_envelopes(id),
    signer_id TEXT NOT NULL, user_id TEXT NOT NULL, channel TEXT NOT NULL, destination_masked TEXT NOT NULL,
    expires_at TEXT NOT NULL, attempts INTEGER NOT NULL DEFAULT 0, max_attempts INTEGER NOT NULL DEFAULT 5,
    delivery_state TEXT NOT NULL DEFAULT 'queued', delivery_provider TEXT, delivery_message_id TEXT,
    delivery_error_code TEXT, delivered_at TEXT, consumed_at TEXT, created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS signature_attempts (
    id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, envelope_id TEXT NOT NULL REFERENCES signature_envelopes(id),
    signer_id TEXT, provider TEXT NOT NULL, action TEXT NOT NULL, state TEXT NOT NULL,
    request_json TEXT NOT NULL DEFAULT '{}', response_json TEXT NOT NULL DEFAULT '{}', error TEXT,
    correlation_id TEXT, created_at TEXT NOT NULL, finished_at TEXT
);
CREATE TABLE IF NOT EXISTS signature_validations (
    id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, envelope_id TEXT NOT NULL REFERENCES signature_envelopes(id),
    valid INTEGER NOT NULL, document_hash_valid INTEGER NOT NULL, evidence_valid INTEGER NOT NULL,
    details_json TEXT NOT NULL DEFAULT '{}', validated_by TEXT, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS signature_artifacts (
    id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, envelope_id TEXT NOT NULL REFERENCES signature_envelopes(id),
    signer_id TEXT NOT NULL, provider TEXT NOT NULL, artifact_type TEXT NOT NULL, sha256 TEXT NOT NULL,
    storage_key TEXT NOT NULL, certificate_subject TEXT, certificate_serial TEXT, metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL, UNIQUE(tenant_id, envelope_id, signer_id, provider, sha256)
);

CREATE TABLE IF NOT EXISTS signature_evidence_packages (
    id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, envelope_id TEXT NOT NULL REFERENCES signature_envelopes(id),
    sha256 TEXT NOT NULL, payload_json TEXT NOT NULL, created_at TEXT NOT NULL,
    UNIQUE(tenant_id, envelope_id, sha256)
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

-- Mail metadata/cache. Conteúdo oficial permanece no servidor IMAP/Mailcow.
CREATE TABLE IF NOT EXISTS mail_accounts (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    person_id TEXT,
    email TEXT NOT NULL COLLATE NOCASE,
    display_name TEXT,
    provider_connection_id TEXT NOT NULL REFERENCES integration_connections(id),
    credential_secret_reference TEXT,
    mode TEXT NOT NULL DEFAULT 'generic_imap_smtp',
    state TEXT NOT NULL DEFAULT 'active',
    quota_mb INTEGER,
    last_sync_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(tenant_id, email),
    UNIQUE(tenant_id, user_id)
);
CREATE TABLE IF NOT EXISTS mail_folders (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    account_id TEXT NOT NULL REFERENCES mail_accounts(id),
    remote_name TEXT NOT NULL,
    display_name TEXT NOT NULL,
    special_use TEXT,
    uid_validity TEXT,
    highest_uid INTEGER NOT NULL DEFAULT 0,
    unread_count INTEGER NOT NULL DEFAULT 0,
    total_count INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(tenant_id, account_id, remote_name)
);
CREATE TABLE IF NOT EXISTS mail_message_metadata (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    account_id TEXT NOT NULL REFERENCES mail_accounts(id),
    folder_id TEXT NOT NULL REFERENCES mail_folders(id),
    remote_uid INTEGER NOT NULL,
    message_id TEXT,
    thread_key TEXT,
    in_reply_to TEXT,
    subject TEXT,
    sender_json TEXT NOT NULL DEFAULT '{}',
    recipients_json TEXT NOT NULL DEFAULT '[]',
    cc_json TEXT NOT NULL DEFAULT '[]',
    bcc_json TEXT NOT NULL DEFAULT '[]',
    sent_at TEXT,
    received_at TEXT,
    flags_json TEXT NOT NULL DEFAULT '[]',
    size_bytes INTEGER,
    has_attachments INTEGER NOT NULL DEFAULT 0,
    preview TEXT,
    content_sha256 TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(tenant_id, account_id, folder_id, remote_uid)
);
CREATE INDEX IF NOT EXISTS idx_mail_message_account_received ON mail_message_metadata(tenant_id, account_id, received_at);
CREATE TABLE IF NOT EXISTS mail_drafts (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    account_id TEXT NOT NULL REFERENCES mail_accounts(id),
    subject TEXT,
    to_json TEXT NOT NULL DEFAULT '[]',
    cc_json TEXT NOT NULL DEFAULT '[]',
    bcc_json TEXT NOT NULL DEFAULT '[]',
    body_text TEXT NOT NULL DEFAULT '',
    body_html TEXT,
    attachments_json TEXT NOT NULL DEFAULT '[]',
    state TEXT NOT NULL DEFAULT 'draft',
    provider_message_id TEXT,
    version INTEGER NOT NULL DEFAULT 1,
    created_by TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS mail_sync_runs (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    account_id TEXT NOT NULL REFERENCES mail_accounts(id),
    state TEXT NOT NULL,
    folders_synced INTEGER NOT NULL DEFAULT 0,
    messages_synced INTEGER NOT NULL DEFAULT 0,
    error_code TEXT,
    error_message TEXT,
    started_at TEXT NOT NULL,
    finished_at TEXT
);
CREATE TABLE IF NOT EXISTS mail_delegations (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    account_id TEXT NOT NULL REFERENCES mail_accounts(id),
    delegate_user_id TEXT NOT NULL,
    can_read INTEGER NOT NULL DEFAULT 1,
    can_send INTEGER NOT NULL DEFAULT 0,
    valid_from TEXT,
    valid_until TEXT,
    state TEXT NOT NULL DEFAULT 'active',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(tenant_id, account_id, delegate_user_id)
);

-- Reporting: execuções e artifacts imutáveis no storage do tenant.
CREATE TABLE IF NOT EXISTS report_runs (
    id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, report_code TEXT NOT NULL, format TEXT NOT NULL,
    parameters_json TEXT NOT NULL DEFAULT '{}', state TEXT NOT NULL, rows_count INTEGER NOT NULL DEFAULT 0,
    requested_by TEXT NOT NULL, requested_at TEXT NOT NULL, started_at TEXT, finished_at TEXT,
    error_code TEXT, error_message TEXT
);
CREATE INDEX IF NOT EXISTS idx_report_runs_tenant_requested ON report_runs(tenant_id, requested_at);
CREATE TABLE IF NOT EXISTS report_artifacts (
    id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, report_run_id TEXT NOT NULL REFERENCES report_runs(id),
    filename TEXT NOT NULL, mime_type TEXT NOT NULL, bytes INTEGER NOT NULL, sha256 TEXT NOT NULL,
    storage_key TEXT NOT NULL, created_at TEXT NOT NULL, UNIQUE(tenant_id, sha256, report_run_id)
);
