"""Control Plane inicial do PIGE360 alinhado ao contrato do runtime.

Revision ID: 0001_control
Revises:
"""
from alembic import op

revision = "0001_control"
down_revision = None
branch_labels = ("control",)
depends_on = None

SQL = r"""
CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE TABLE platform_tenants (
    id text PRIMARY KEY,
    code varchar(63) NOT NULL UNIQUE,
    legal_name varchar(300) NOT NULL,
    trade_name varchar(200) NOT NULL,
    status varchar(40) NOT NULL,
    database_path text,
    storage_path text NOT NULL,
    database_name varchar(63) UNIQUE,
    database_user varchar(63) UNIQUE,
    database_secret_ciphertext text,
    bucket_name varchar(63) UNIQUE,
    storage_prefix text,
    encryption_key_reference text,
    quotas_json text NOT NULL DEFAULT '{}',
    version integer NOT NULL DEFAULT 1 CHECK (version > 0),
    created_at text NOT NULL,
    updated_at text NOT NULL
);
CREATE TABLE tenant_domains (
    id text PRIMARY KEY,
    tenant_id text NOT NULL REFERENCES platform_tenants(id) ON DELETE RESTRICT,
    hostname varchar(253) NOT NULL UNIQUE,
    surface varchar(40) NOT NULL DEFAULT 'admin',
    status varchar(40) NOT NULL,
    is_canonical integer NOT NULL DEFAULT 0,
    certificate_policy varchar(40) NOT NULL DEFAULT 'cloudflare_managed',
    certificate_status varchar(40) NOT NULL DEFAULT 'not_requested',
    created_at text NOT NULL,
    updated_at text
);
CREATE UNIQUE INDEX uq_tenant_canonical_surface ON tenant_domains(tenant_id, surface) WHERE is_canonical=1;
CREATE TABLE users (
    id text PRIMARY KEY,
    tenant_id text,
    person_id text,
    email varchar(320) NOT NULL,
    password_hash text NOT NULL,
    roles_json text NOT NULL,
    active integer NOT NULL DEFAULT 1,
    created_at text NOT NULL,
    updated_at text NOT NULL,
    UNIQUE(tenant_id,email)
);
CREATE UNIQUE INDEX uq_platform_user_email ON users(lower(email)) WHERE tenant_id IS NULL;
CREATE TABLE refresh_tokens (
    jti text PRIMARY KEY,
    user_id text NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    tenant_id text,
    token_hash text NOT NULL UNIQUE,
    expires_at text NOT NULL,
    revoked_at text,
    replaced_by text,
    created_at text NOT NULL
);
CREATE TABLE support_sessions (
    id text PRIMARY KEY,
    platform_admin_id text NOT NULL REFERENCES users(id),
    tenant_id text NOT NULL REFERENCES platform_tenants(id),
    assumed_user_id text,
    reason text NOT NULL,
    ticket varchar(200),
    ip text,
    device text,
    started_at text NOT NULL,
    expires_at text NOT NULL,
    ended_at text
);
CREATE TABLE audit_log (
    id text PRIMARY KEY,
    tenant_id text REFERENCES platform_tenants(id),
    actor_id text,
    action varchar(120) NOT NULL,
    aggregate_type varchar(120) NOT NULL,
    aggregate_id text,
    before_json text,
    after_json text,
    reason text,
    correlation_id text NOT NULL,
    created_at text NOT NULL
);
CREATE INDEX ix_platform_audit_scope ON audit_log(tenant_id, created_at DESC);
CREATE TABLE outbox_events (
    id text PRIMARY KEY,
    tenant_id text REFERENCES platform_tenants(id),
    event_type varchar(160) NOT NULL,
    event_version integer NOT NULL DEFAULT 1,
    aggregate_type varchar(120) NOT NULL,
    aggregate_id text NOT NULL,
    payload_json text NOT NULL,
    correlation_id text NOT NULL,
    created_at text NOT NULL,
    published_at text,
    attempts integer NOT NULL DEFAULT 0,
    next_attempt_at text,
    last_error text
);
CREATE INDEX ix_platform_outbox_pending ON outbox_events(created_at) WHERE published_at IS NULL;
CREATE TABLE tenant_provisioning_runs (
    id text PRIMARY KEY,
    tenant_id text NOT NULL REFERENCES platform_tenants(id),
    idempotency_key varchar(200) NOT NULL,
    state varchar(60) NOT NULL,
    step varchar(120) NOT NULL,
    input_hash char(64) NOT NULL,
    result_json text,
    attempts integer NOT NULL DEFAULT 0,
    started_at text NOT NULL,
    finished_at text,
    UNIQUE(tenant_id,idempotency_key)
);
CREATE TABLE platform_releases (
    id text PRIMARY KEY,
    version varchar(64) NOT NULL UNIQUE,
    channel varchar(32) NOT NULL,
    manifest_sha256 char(64) NOT NULL,
    status varchar(32) NOT NULL,
    artifacts_json text NOT NULL DEFAULT '[]',
    created_at text NOT NULL
);
"""


def upgrade() -> None:
    op.execute(SQL)


def downgrade() -> None:
    op.execute(r"""
    DROP TABLE IF EXISTS platform_releases;
    DROP TABLE IF EXISTS tenant_provisioning_runs;
    DROP TABLE IF EXISTS outbox_events;
    DROP TABLE IF EXISTS audit_log;
    DROP TABLE IF EXISTS support_sessions;
    DROP TABLE IF EXISTS refresh_tokens;
    DROP TABLE IF EXISTS users;
    DROP TABLE IF EXISTS tenant_domains;
    DROP TABLE IF EXISTS platform_tenants;
    """)
