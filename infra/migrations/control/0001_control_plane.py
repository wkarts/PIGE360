"""Control Plane inicial do PIGE360.

Revision ID: 0001_control
Revises:
"""
from alembic import op

revision = "0001_control"
down_revision = None
branch_labels = ("control",)
depends_on = None

SQL = r'''
CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE TABLE platform_tenants (
    id uuid PRIMARY KEY,
    code varchar(63) NOT NULL UNIQUE,
    legal_name varchar(300) NOT NULL,
    trade_name varchar(200) NOT NULL,
    status varchar(40) NOT NULL CHECK (status IN ('draft','provisioning','active','degraded','suspended','failed','archived')),
    database_name varchar(63) NOT NULL UNIQUE,
    database_user varchar(63) NOT NULL UNIQUE,
    secret_reference text NOT NULL,
    storage_prefix text NOT NULL UNIQUE,
    bucket_name varchar(63) NOT NULL UNIQUE,
    encryption_key_reference text NOT NULL,
    quotas jsonb NOT NULL DEFAULT '{}'::jsonb,
    version integer NOT NULL DEFAULT 1 CHECK (version > 0),
    created_at timestamptz NOT NULL,
    updated_at timestamptz NOT NULL
);
CREATE TABLE tenant_domains (
    id uuid PRIMARY KEY,
    tenant_id uuid NOT NULL REFERENCES platform_tenants(id) ON DELETE RESTRICT,
    hostname citext NOT NULL UNIQUE,
    surface varchar(40) NOT NULL,
    status varchar(40) NOT NULL,
    is_canonical boolean NOT NULL DEFAULT false,
    certificate_policy varchar(40) NOT NULL DEFAULT 'cloudflare_managed',
    certificate_status varchar(40) NOT NULL DEFAULT 'not_requested',
    created_at timestamptz NOT NULL,
    updated_at timestamptz NOT NULL
);
CREATE UNIQUE INDEX uq_tenant_canonical_surface ON tenant_domains(tenant_id, surface) WHERE is_canonical;
CREATE TABLE platform_users (
    id uuid PRIMARY KEY,
    email citext NOT NULL UNIQUE,
    password_hash text NOT NULL,
    roles jsonb NOT NULL,
    active boolean NOT NULL DEFAULT true,
    mfa_required boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL,
    updated_at timestamptz NOT NULL
);
CREATE TABLE platform_refresh_tokens (
    jti uuid PRIMARY KEY,
    user_id uuid NOT NULL REFERENCES platform_users(id) ON DELETE CASCADE,
    token_hash char(64) NOT NULL UNIQUE,
    expires_at timestamptz NOT NULL,
    revoked_at timestamptz,
    replaced_by uuid,
    created_at timestamptz NOT NULL
);
CREATE TABLE support_sessions (
    id uuid PRIMARY KEY,
    platform_admin_id uuid NOT NULL REFERENCES platform_users(id),
    tenant_id uuid NOT NULL REFERENCES platform_tenants(id),
    assumed_user_id uuid,
    reason text NOT NULL,
    ticket varchar(200),
    ip inet,
    device text,
    started_at timestamptz NOT NULL,
    expires_at timestamptz NOT NULL,
    ended_at timestamptz,
    CONSTRAINT support_session_time CHECK (expires_at > started_at)
);
CREATE TABLE platform_audit_log (
    id uuid PRIMARY KEY,
    tenant_id uuid REFERENCES platform_tenants(id),
    actor_id uuid REFERENCES platform_users(id),
    action varchar(120) NOT NULL,
    aggregate_type varchar(120) NOT NULL,
    aggregate_id uuid,
    before_json jsonb,
    after_json jsonb,
    reason text,
    correlation_id uuid NOT NULL,
    ip inet,
    user_agent text,
    created_at timestamptz NOT NULL
);
CREATE INDEX ix_platform_audit_scope ON platform_audit_log(tenant_id, created_at DESC);
CREATE TABLE platform_outbox_events (
    id uuid PRIMARY KEY,
    tenant_id uuid REFERENCES platform_tenants(id),
    event_type varchar(160) NOT NULL,
    event_version integer NOT NULL DEFAULT 1,
    aggregate_type varchar(120) NOT NULL,
    aggregate_id uuid NOT NULL,
    payload_json jsonb NOT NULL,
    correlation_id uuid NOT NULL,
    created_at timestamptz NOT NULL,
    published_at timestamptz,
    attempts integer NOT NULL DEFAULT 0,
    next_attempt_at timestamptz,
    last_error text
);
CREATE INDEX ix_platform_outbox_pending ON platform_outbox_events(next_attempt_at, created_at) WHERE published_at IS NULL;
CREATE TABLE tenant_provisioning_runs (
    id uuid PRIMARY KEY,
    tenant_id uuid NOT NULL REFERENCES platform_tenants(id),
    idempotency_key varchar(200) NOT NULL,
    state varchar(60) NOT NULL,
    step varchar(120) NOT NULL,
    input_hash char(64) NOT NULL,
    result_json jsonb,
    attempts integer NOT NULL DEFAULT 0,
    started_at timestamptz NOT NULL,
    finished_at timestamptz,
    UNIQUE(tenant_id, idempotency_key)
);
CREATE TABLE platform_releases (
    id uuid PRIMARY KEY,
    version varchar(64) NOT NULL UNIQUE,
    channel varchar(32) NOT NULL,
    manifest_sha256 char(64) NOT NULL,
    status varchar(32) NOT NULL,
    artifacts jsonb NOT NULL DEFAULT '[]'::jsonb,
    created_at timestamptz NOT NULL
);
'''


def upgrade() -> None:
    op.execute(SQL)


def downgrade() -> None:
    op.execute('''
    DROP TABLE IF EXISTS platform_releases;
    DROP TABLE IF EXISTS tenant_provisioning_runs;
    DROP TABLE IF EXISTS platform_outbox_events;
    DROP TABLE IF EXISTS platform_audit_log;
    DROP TABLE IF EXISTS support_sessions;
    DROP TABLE IF EXISTS platform_refresh_tokens;
    DROP TABLE IF EXISTS platform_users;
    DROP TABLE IF EXISTS tenant_domains;
    DROP TABLE IF EXISTS platform_tenants;
    ''')
