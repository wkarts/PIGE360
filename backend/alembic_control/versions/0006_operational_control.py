"""Registra agentes e jobs operacionais tipados no Control Plane.

Revision ID: 0006_operational_control
Revises: 0005_tenant_api_rate_quota
"""
from alembic import op


revision = "0006_operational_control"
down_revision = "0005_tenant_api_rate_quota"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """CREATE TABLE IF NOT EXISTS operational_agents (
               id text PRIMARY KEY,
               name varchar(120) NOT NULL UNIQUE,
               agent_type varchar(32) NOT NULL
                   CHECK(agent_type IN ('host', 'backup', 'restore', 'deploy', 'multi')),
               capabilities_json text NOT NULL,
               token_hash char(64) NOT NULL UNIQUE,
               software_version varchar(64),
               state varchar(32) NOT NULL DEFAULT 'active'
                   CHECK(state IN ('active', 'revoked')),
               registered_by text NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
               last_seen_at text,
               revoked_at text,
               created_at text NOT NULL,
               updated_at text NOT NULL,
               version integer NOT NULL DEFAULT 1 CHECK(version > 0)
           )"""
    )
    op.execute(
        """CREATE TABLE IF NOT EXISTS operational_jobs (
               id text PRIMARY KEY,
               operation_type varchar(32) NOT NULL
                   CHECK(operation_type IN ('backup', 'restore', 'deploy')),
               resource_scope varchar(32) NOT NULL
                   CHECK(resource_scope IN ('platform', 'tenant')),
               tenant_id text REFERENCES platform_tenants(id) ON DELETE RESTRICT,
               required_capability varchar(64) NOT NULL,
               deployment_target varchar(32),
               image_mode varchar(32),
               release_version varchar(64),
               backup_reference varchar(200),
               state varchar(32) NOT NULL DEFAULT 'queued'
                   CHECK(state IN ('queued', 'claimed', 'running', 'succeeded', 'failed', 'cancelled')),
               idempotency_key varchar(200) NOT NULL,
               request_hash char(64) NOT NULL,
               reason text NOT NULL,
               requested_by text NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
               assigned_agent_id text REFERENCES operational_agents(id) ON DELETE RESTRICT,
               attempts integer NOT NULL DEFAULT 0 CHECK(attempts >= 0),
               result_code varchar(80),
               evidence_reference varchar(240),
               evidence_sha256 char(64),
               failure_code varchar(80),
               correlation_id text NOT NULL,
               claimed_at text,
               started_at text,
               finished_at text,
               lease_expires_at text,
               created_at text NOT NULL,
               updated_at text NOT NULL,
               version integer NOT NULL DEFAULT 1 CHECK(version > 0),
               UNIQUE(operation_type, idempotency_key),
               CHECK(
                   (resource_scope = 'platform' AND tenant_id IS NULL)
                   OR (resource_scope = 'tenant' AND tenant_id IS NOT NULL)
               )
           )"""
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_operational_agents_state_seen "
        "ON operational_agents(state, last_seen_at)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_operational_jobs_queue "
        "ON operational_jobs(state, required_capability, created_at)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_operational_jobs_agent "
        "ON operational_jobs(assigned_agent_id, state, updated_at)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_operational_jobs_tenant "
        "ON operational_jobs(tenant_id, created_at)"
    )


def downgrade() -> None:
    # Jobs e agentes compõem a trilha operacional/auditoria. Um rollback de
    # aplicação não deve apagar essa evidência; somente os índices são reversíveis.
    op.execute("DROP INDEX IF EXISTS ix_operational_jobs_tenant")
    op.execute("DROP INDEX IF EXISTS ix_operational_jobs_agent")
    op.execute("DROP INDEX IF EXISTS ix_operational_jobs_queue")
    op.execute("DROP INDEX IF EXISTS ix_operational_agents_state_seen")
