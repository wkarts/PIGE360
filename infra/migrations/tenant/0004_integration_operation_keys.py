"""Idempotência durável das operações em providers externos.

Revision ID: 0004_integration_operation_keys
Revises: 0003_academic_periods
"""
from alembic import op

revision = "0004_integration_operation_keys"
down_revision = "0003_academic_periods"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
    CREATE TABLE IF NOT EXISTS integration_operation_keys (
      tenant_id TEXT NOT NULL,
      connection_id TEXT NOT NULL REFERENCES integration_connections(id),
      idempotency_key TEXT NOT NULL,
      capability TEXT NOT NULL,
      request_hash TEXT NOT NULL,
      state TEXT NOT NULL,
      response_json TEXT,
      error TEXT,
      created_at TEXT NOT NULL,
      updated_at TEXT NOT NULL,
      PRIMARY KEY(tenant_id, connection_id, idempotency_key)
    )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_integration_operation_state ON integration_operation_keys(tenant_id, connection_id, state, updated_at)")
    op.execute("ALTER TABLE integration_operation_keys ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE integration_operation_keys FORCE ROW LEVEL SECURITY")
    op.execute("DROP POLICY IF EXISTS pige360_tenant_integration_operation_keys ON integration_operation_keys")
    op.execute("CREATE POLICY pige360_tenant_integration_operation_keys ON integration_operation_keys USING (tenant_id = current_setting('app.tenant_id', true)) WITH CHECK (tenant_id = current_setting('app.tenant_id', true))")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS integration_operation_keys")
