PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS platform_tenants (
    id TEXT PRIMARY KEY,
    code TEXT NOT NULL UNIQUE,
    legal_name TEXT NOT NULL,
    trade_name TEXT NOT NULL,
    status TEXT NOT NULL,
    database_path TEXT NOT NULL UNIQUE,
    storage_path TEXT NOT NULL UNIQUE,
    quotas_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    version INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS tenant_domains (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL REFERENCES platform_tenants(id),
    hostname TEXT NOT NULL UNIQUE,
    surface TEXT NOT NULL DEFAULT 'admin',
    status TEXT NOT NULL,
    is_canonical INTEGER NOT NULL DEFAULT 0,
    certificate_policy TEXT NOT NULL DEFAULT 'canonical_wildcard',
    certificate_status TEXT NOT NULL DEFAULT 'active',
    verification_method TEXT,
    verification_name TEXT,
    verification_token TEXT,
    verification_status TEXT NOT NULL DEFAULT 'not_required',
    provider TEXT DEFAULT 'platform_wildcard',
    provider_reference TEXT,
    provider_validation_json TEXT NOT NULL DEFAULT '{}',
    verified_at TEXT,
    activated_at TEXT,
    last_error TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT
);

CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    tenant_id TEXT,
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
    tenant_id TEXT,
    token_hash TEXT NOT NULL UNIQUE,
    family_id TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    revoked_at TEXT,
    replaced_by TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS auth_login_attempts (
    identifier_hash TEXT PRIMARY KEY,
    tenant_id TEXT,
    failed_attempts INTEGER NOT NULL CHECK(failed_attempts >= 0),
    window_started_at TEXT NOT NULL,
    locked_until TEXT,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS tenant_api_rate_buckets (
    tenant_id TEXT NOT NULL REFERENCES platform_tenants(id) ON DELETE CASCADE,
    bucket_start TEXT NOT NULL,
    request_count INTEGER NOT NULL CHECK(request_count >= 0),
    updated_at TEXT NOT NULL,
    PRIMARY KEY (tenant_id, bucket_start)
);

CREATE INDEX IF NOT EXISTS ix_tenant_api_rate_buckets_updated
    ON tenant_api_rate_buckets(updated_at);

-- Administração comercial do Control Plane. Esta estrutura é deliberadamente
-- separada de provisioning e quotas operacionais para manter a evolução aditiva.
CREATE TABLE IF NOT EXISTS commercial_partners (
    id TEXT PRIMARY KEY,
    code TEXT NOT NULL UNIQUE,
    legal_name TEXT NOT NULL,
    trade_name TEXT NOT NULL,
    contact_email TEXT,
    notes TEXT,
    status TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active','suspended','archived')),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    version INTEGER NOT NULL DEFAULT 1 CHECK(version > 0)
);

CREATE INDEX IF NOT EXISTS ix_commercial_partners_status
    ON commercial_partners(status, trade_name);

CREATE TABLE IF NOT EXISTS commercial_partner_tenants (
    tenant_id TEXT PRIMARY KEY REFERENCES platform_tenants(id) ON DELETE CASCADE,
    partner_id TEXT NOT NULL REFERENCES commercial_partners(id) ON DELETE RESTRICT,
    linked_by TEXT,
    linked_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_commercial_partner_tenants_partner
    ON commercial_partner_tenants(partner_id, linked_at);

CREATE TABLE IF NOT EXISTS commercial_plans (
    id TEXT PRIMARY KEY,
    code TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    description TEXT,
    currency TEXT NOT NULL DEFAULT 'BRL',
    billing_interval TEXT NOT NULL DEFAULT 'monthly' CHECK(billing_interval IN ('monthly','annual','custom')),
    price_minor INTEGER NOT NULL DEFAULT 0 CHECK(price_minor >= 0),
    features_json TEXT NOT NULL DEFAULT '{}',
    limits_json TEXT NOT NULL DEFAULT '{}',
    status TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active','inactive','archived')),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    version INTEGER NOT NULL DEFAULT 1 CHECK(version > 0)
);

CREATE INDEX IF NOT EXISTS ix_commercial_plans_status
    ON commercial_plans(status, name);

CREATE TABLE IF NOT EXISTS commercial_subscriptions (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL UNIQUE REFERENCES platform_tenants(id) ON DELETE CASCADE,
    plan_id TEXT NOT NULL REFERENCES commercial_plans(id) ON DELETE RESTRICT,
    status TEXT NOT NULL CHECK(status IN ('active','trialing','suspended','canceled')),
    starts_at TEXT NOT NULL,
    current_period_end TEXT,
    trial_ends_at TEXT,
    cancel_at_period_end INTEGER NOT NULL DEFAULT 0,
    billing_mode TEXT NOT NULL DEFAULT 'manual' CHECK(billing_mode='manual'),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    version INTEGER NOT NULL DEFAULT 1 CHECK(version > 0)
);

CREATE INDEX IF NOT EXISTS ix_commercial_subscriptions_plan_status
    ON commercial_subscriptions(plan_id, status);

CREATE TABLE IF NOT EXISTS commercial_usage_snapshots (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL REFERENCES platform_tenants(id) ON DELETE CASCADE,
    period TEXT NOT NULL,
    source TEXT NOT NULL,
    metrics_json TEXT NOT NULL DEFAULT '{}',
    captured_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    version INTEGER NOT NULL DEFAULT 1 CHECK(version > 0),
    UNIQUE(tenant_id, period, source)
);

CREATE INDEX IF NOT EXISTS ix_commercial_usage_tenant_period
    ON commercial_usage_snapshots(tenant_id, period, captured_at);

CREATE TABLE IF NOT EXISTS commercial_idempotency_records (
    scope TEXT NOT NULL,
    idempotency_key TEXT NOT NULL,
    request_hash TEXT NOT NULL,
    response_json TEXT,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    PRIMARY KEY(scope, idempotency_key)
);

CREATE INDEX IF NOT EXISTS ix_commercial_idempotency_expires
    ON commercial_idempotency_records(expires_at);

CREATE TABLE IF NOT EXISTS support_sessions (
    id TEXT PRIMARY KEY,
    platform_admin_id TEXT NOT NULL,
    tenant_id TEXT NOT NULL REFERENCES platform_tenants(id),
    assumed_user_id TEXT,
    reason TEXT NOT NULL,
    ticket TEXT,
    ip TEXT,
    device TEXT,
    started_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    ended_at TEXT
);

CREATE TABLE IF NOT EXISTS audit_log (
    id TEXT PRIMARY KEY,
    tenant_id TEXT,
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
    tenant_id TEXT,
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
CREATE INDEX IF NOT EXISTS idx_control_inbox_event_consumer ON inbox_events(tenant_id,event_id,consumer);

CREATE INDEX IF NOT EXISTS idx_domains_tenant ON tenant_domains(tenant_id);
-- Compatível com bancos SQLite legados: as colunas de lifecycle são adicionadas
-- depois por SQLiteStore._apply_compatibility_migrations(). O índice composto de
-- lifecycle permanece no PostgreSQL/Alembic, onde a migration controla a ordem.
CREATE INDEX IF NOT EXISTS idx_domains_status ON tenant_domains(status);
CREATE INDEX IF NOT EXISTS idx_control_outbox_pending ON outbox_events(published_at, created_at);
CREATE INDEX IF NOT EXISTS idx_control_auth_login_attempts_updated ON auth_login_attempts(updated_at);

-- Administração operacional do Control Plane. Tokens de agentes são persistidos
-- somente como SHA-256 e jobs aceitam exclusivamente parâmetros tipados pela API.
CREATE TABLE IF NOT EXISTS operational_agents (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    agent_type TEXT NOT NULL CHECK(agent_type IN ('host', 'backup', 'restore', 'deploy', 'multi')),
    capabilities_json TEXT NOT NULL,
    token_hash TEXT NOT NULL UNIQUE,
    software_version TEXT,
    state TEXT NOT NULL DEFAULT 'active' CHECK(state IN ('active', 'revoked')),
    registered_by TEXT NOT NULL REFERENCES users(id),
    last_seen_at TEXT,
    revoked_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    version INTEGER NOT NULL DEFAULT 1 CHECK(version > 0)
);

CREATE TABLE IF NOT EXISTS operational_jobs (
    id TEXT PRIMARY KEY,
    operation_type TEXT NOT NULL CHECK(operation_type IN ('backup', 'restore', 'deploy')),
    resource_scope TEXT NOT NULL CHECK(resource_scope IN ('platform', 'tenant')),
    tenant_id TEXT REFERENCES platform_tenants(id),
    required_capability TEXT NOT NULL,
    deployment_target TEXT,
    image_mode TEXT,
    release_version TEXT,
    backup_reference TEXT,
    state TEXT NOT NULL DEFAULT 'queued'
        CHECK(state IN ('queued', 'claimed', 'running', 'succeeded', 'failed', 'cancelled')),
    idempotency_key TEXT NOT NULL,
    request_hash TEXT NOT NULL,
    reason TEXT NOT NULL,
    requested_by TEXT NOT NULL REFERENCES users(id),
    assigned_agent_id TEXT REFERENCES operational_agents(id),
    attempts INTEGER NOT NULL DEFAULT 0 CHECK(attempts >= 0),
    result_code TEXT,
    evidence_reference TEXT,
    evidence_sha256 TEXT,
    failure_code TEXT,
    correlation_id TEXT NOT NULL,
    claimed_at TEXT,
    started_at TEXT,
    finished_at TEXT,
    lease_expires_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    version INTEGER NOT NULL DEFAULT 1 CHECK(version > 0),
    UNIQUE(operation_type, idempotency_key),
    CHECK(
        (resource_scope = 'platform' AND tenant_id IS NULL)
        OR (resource_scope = 'tenant' AND tenant_id IS NOT NULL)
    )
);

CREATE INDEX IF NOT EXISTS idx_operational_agents_state_seen
    ON operational_agents(state, last_seen_at);
CREATE INDEX IF NOT EXISTS idx_operational_jobs_queue
    ON operational_jobs(state, required_capability, created_at);
CREATE INDEX IF NOT EXISTS idx_operational_jobs_agent
    ON operational_jobs(assigned_agent_id, state, updated_at);
CREATE INDEX IF NOT EXISTS idx_operational_jobs_tenant
    ON operational_jobs(tenant_id, created_at);
