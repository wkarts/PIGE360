"""Reporting runs and immutable artifacts.

Revision ID: 0012_reporting
Revises: 0011_mail_metadata
"""
from alembic import op
revision="0012_reporting";down_revision="0011_mail_metadata";branch_labels=None;depends_on=None
TABLES=("report_runs","report_artifacts")
def upgrade()->None:
    op.execute("""
    CREATE TABLE IF NOT EXISTS report_runs (
      id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, report_code TEXT NOT NULL, format TEXT NOT NULL,
      parameters_json TEXT NOT NULL DEFAULT '{}', state TEXT NOT NULL, rows_count INTEGER NOT NULL DEFAULT 0,
      requested_by TEXT NOT NULL, requested_at TEXT NOT NULL, started_at TEXT, finished_at TEXT,
      error_code TEXT, error_message TEXT
    );
    CREATE INDEX IF NOT EXISTS idx_report_runs_tenant_requested ON report_runs(tenant_id,requested_at);
    CREATE TABLE IF NOT EXISTS report_artifacts (
      id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, report_run_id TEXT NOT NULL REFERENCES report_runs(id),
      filename TEXT NOT NULL, mime_type TEXT NOT NULL, bytes BIGINT NOT NULL, sha256 TEXT NOT NULL,
      storage_key TEXT NOT NULL, created_at TEXT NOT NULL, UNIQUE(tenant_id,sha256,report_run_id)
    );
    """)
    for table in TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"DROP POLICY IF EXISTS {table}_tenant_isolation ON {table}")
        op.execute(f"CREATE POLICY {table}_tenant_isolation ON {table} USING (tenant_id=current_setting('app.tenant_id',true)) WITH CHECK (tenant_id=current_setting('app.tenant_id',true))")
def downgrade()->None:
    for table in reversed(TABLES): op.execute(f"DROP TABLE IF EXISTS {table}")
