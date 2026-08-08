"""IBPT WWSoftwares versioned catalogs.

Revision ID: 0010_ibpt_catalogs
Revises: 0009_signature_otp_delivery
"""
from alembic import op

revision = "0010_ibpt_catalogs"
down_revision = "0009_signature_otp_delivery"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
    CREATE TABLE IF NOT EXISTS ibpt_sync_runs (
      id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, uf TEXT NOT NULL,
      state TEXT NOT NULL DEFAULT 'queued', snapshot_id TEXT, requested_by TEXT,
      requested_at TEXT NOT NULL, started_at TEXT, finished_at TEXT,
      error_code TEXT, error_message TEXT
    );
    CREATE INDEX IF NOT EXISTS ix_ibpt_sync_runs_state ON ibpt_sync_runs(tenant_id, state, requested_at);
    CREATE TABLE IF NOT EXISTS ibpt_snapshots (
      id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, uf TEXT NOT NULL,
      source_url TEXT NOT NULL, sha256 TEXT NOT NULL, storage_key TEXT NOT NULL,
      rows_count INTEGER NOT NULL, source_version TEXT, effective_from TEXT, effective_to TEXT,
      state TEXT NOT NULL DEFAULT 'active', created_at TEXT NOT NULL,
      UNIQUE(tenant_id, uf, sha256)
    );
    CREATE INDEX IF NOT EXISTS ix_ibpt_snapshots_active ON ibpt_snapshots(tenant_id, uf, state, created_at);
    CREATE TABLE IF NOT EXISTS ibpt_rates (
      id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, snapshot_id TEXT NOT NULL REFERENCES ibpt_snapshots(id),
      uf TEXT NOT NULL, code TEXT NOT NULL, ex TEXT NOT NULL DEFAULT '', item_type TEXT NOT NULL DEFAULT '',
      description TEXT NOT NULL, national_federal NUMERIC NOT NULL DEFAULT 0,
      imported_federal NUMERIC NOT NULL DEFAULT 0, state_rate NUMERIC NOT NULL DEFAULT 0,
      municipal_rate NUMERIC NOT NULL DEFAULT 0, effective_from TEXT, effective_to TEXT,
      source_version TEXT, source_name TEXT, created_at TEXT NOT NULL,
      UNIQUE(tenant_id, snapshot_id, code, ex, item_type)
    );
    CREATE INDEX IF NOT EXISTS ix_ibpt_rates_lookup ON ibpt_rates(tenant_id, uf, code, snapshot_id);
    """)
    for table in ("ibpt_sync_runs", "ibpt_snapshots", "ibpt_rates"):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"DROP POLICY IF EXISTS {table}_tenant_isolation ON {table}")
        op.execute(
            f"CREATE POLICY {table}_tenant_isolation ON {table} "
            "USING (tenant_id = current_setting('app.tenant_id', true)) "
            "WITH CHECK (tenant_id = current_setting('app.tenant_id', true))"
        )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS ibpt_rates")
    op.execute("DROP TABLE IF EXISTS ibpt_snapshots")
    op.execute("DROP TABLE IF EXISTS ibpt_sync_runs")
