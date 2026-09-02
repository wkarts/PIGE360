PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS platform_tenants (
    id TEXT PRIMARY KEY,
    code TEXT NOT NULL UNIQUE,
    legal_name TEXT NOT NULL,
    trade_name TEXT NOT NULL,
    status TEXT NOT NULL,
    database_path TEXT NOT NULL UNIQUE,
    storage_path TEXT NOT NULL UNIQUE,
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
    expires_at TEXT NOT NULL,
    revoked_at TEXT,
    replaced_by TEXT,
    created_at TEXT NOT NULL
);

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
CREATE INDEX IF NOT EXISTS idx_domains_status ON tenant_domains(status, verification_status, certificate_status);
CREATE INDEX IF NOT EXISTS idx_control_outbox_pending ON outbox_events(published_at, created_at);
