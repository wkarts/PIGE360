"""Add partner, plan, subscription, usage and entitlement persistence.

Revision ID: 0007_commercial_administration
Revises: 0006_operational_control
"""
from alembic import op


revision = "0007_commercial_administration"
down_revision = "0006_operational_control"
branch_labels = None
depends_on = None


DDL = r"""
CREATE TABLE IF NOT EXISTS commercial_partners (
    id text PRIMARY KEY,
    code varchar(63) NOT NULL UNIQUE,
    legal_name varchar(300) NOT NULL,
    trade_name varchar(200) NOT NULL,
    contact_email varchar(320),
    notes text,
    status varchar(20) NOT NULL DEFAULT 'active' CHECK(status IN ('active','suspended','archived')),
    created_at text NOT NULL,
    updated_at text NOT NULL,
    version integer NOT NULL DEFAULT 1 CHECK(version > 0)
);
CREATE INDEX IF NOT EXISTS ix_commercial_partners_status
    ON commercial_partners(status, trade_name);
CREATE TABLE IF NOT EXISTS commercial_partner_tenants (
    tenant_id text PRIMARY KEY REFERENCES platform_tenants(id) ON DELETE CASCADE,
    partner_id text NOT NULL REFERENCES commercial_partners(id) ON DELETE RESTRICT,
    linked_by text,
    linked_at text NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_commercial_partner_tenants_partner
    ON commercial_partner_tenants(partner_id, linked_at);
CREATE TABLE IF NOT EXISTS commercial_plans (
    id text PRIMARY KEY,
    code varchar(50) NOT NULL UNIQUE,
    name varchar(120) NOT NULL,
    description text,
    currency varchar(3) NOT NULL DEFAULT 'BRL',
    billing_interval varchar(20) NOT NULL DEFAULT 'monthly' CHECK(billing_interval IN ('monthly','annual','custom')),
    price_minor bigint NOT NULL DEFAULT 0 CHECK(price_minor >= 0),
    features_json text NOT NULL DEFAULT '{}',
    limits_json text NOT NULL DEFAULT '{}',
    status varchar(20) NOT NULL DEFAULT 'active' CHECK(status IN ('active','inactive','archived')),
    created_at text NOT NULL,
    updated_at text NOT NULL,
    version integer NOT NULL DEFAULT 1 CHECK(version > 0)
);
CREATE INDEX IF NOT EXISTS ix_commercial_plans_status
    ON commercial_plans(status, name);
CREATE TABLE IF NOT EXISTS commercial_subscriptions (
    id text PRIMARY KEY,
    tenant_id text NOT NULL UNIQUE REFERENCES platform_tenants(id) ON DELETE CASCADE,
    plan_id text NOT NULL REFERENCES commercial_plans(id) ON DELETE RESTRICT,
    status varchar(20) NOT NULL CHECK(status IN ('active','trialing','suspended','canceled')),
    starts_at text NOT NULL,
    current_period_end text,
    trial_ends_at text,
    cancel_at_period_end integer NOT NULL DEFAULT 0,
    billing_mode varchar(20) NOT NULL DEFAULT 'manual' CHECK(billing_mode='manual'),
    created_at text NOT NULL,
    updated_at text NOT NULL,
    version integer NOT NULL DEFAULT 1 CHECK(version > 0)
);
CREATE INDEX IF NOT EXISTS ix_commercial_subscriptions_plan_status
    ON commercial_subscriptions(plan_id, status);
CREATE TABLE IF NOT EXISTS commercial_usage_snapshots (
    id text PRIMARY KEY,
    tenant_id text NOT NULL REFERENCES platform_tenants(id) ON DELETE CASCADE,
    period varchar(7) NOT NULL,
    source varchar(50) NOT NULL,
    metrics_json text NOT NULL DEFAULT '{}',
    captured_at text NOT NULL,
    updated_at text NOT NULL,
    version integer NOT NULL DEFAULT 1 CHECK(version > 0),
    UNIQUE(tenant_id, period, source)
);
CREATE INDEX IF NOT EXISTS ix_commercial_usage_tenant_period
    ON commercial_usage_snapshots(tenant_id, period, captured_at);
CREATE TABLE IF NOT EXISTS commercial_idempotency_records (
    scope varchar(220) NOT NULL,
    idempotency_key varchar(200) NOT NULL,
    request_hash char(64) NOT NULL,
    response_json text,
    created_at text NOT NULL,
    expires_at text NOT NULL,
    PRIMARY KEY(scope, idempotency_key)
);
CREATE INDEX IF NOT EXISTS ix_commercial_idempotency_expires
    ON commercial_idempotency_records(expires_at);
"""


def upgrade() -> None:
    for statement in _statements(DDL):
        op.execute(statement)


def _statements(sql: str) -> tuple[str, ...]:
    """Entrega uma instrução por chamada para compatibilidade com psycopg 3."""

    return tuple(statement.strip() for statement in sql.split(";") if statement.strip())


def downgrade() -> None:
    # Estruturas são novas e independentes. Faça backup antes do downgrade: as
    # tabelas comerciais armazenam histórico que não existe em versões anteriores.
    teardown = r"""
        DROP TABLE IF EXISTS commercial_idempotency_records;
        DROP TABLE IF EXISTS commercial_usage_snapshots;
        DROP TABLE IF EXISTS commercial_subscriptions;
        DROP TABLE IF EXISTS commercial_partner_tenants;
        DROP TABLE IF EXISTS commercial_plans;
        DROP TABLE IF EXISTS commercial_partners;
        """
    for statement in _statements(teardown):
        op.execute(statement)
