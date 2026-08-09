"""Integrações educacionais governamentais: validação, importação e fila de transmissão."""
from alembic import op

revision="0028_government_education_operations"
down_revision="0027_compliance_lgpd"
branch_labels=None
depends_on=None
TABLES=("government_validation_runs","government_validation_issues","government_imports","government_transmissions","government_transmission_events")

def upgrade():
    op.execute("""CREATE TABLE IF NOT EXISTS government_validation_runs(id TEXT PRIMARY KEY,tenant_id TEXT NOT NULL,layout_id TEXT NOT NULL REFERENCES government_export_layouts(id),reference_period TEXT NOT NULL,direction TEXT NOT NULL,state TEXT NOT NULL,record_count INTEGER NOT NULL DEFAULT 0,error_count INTEGER NOT NULL DEFAULT 0,warning_count INTEGER NOT NULL DEFAULT 0,source_sha256 TEXT,created_by TEXT NOT NULL,created_at TIMESTAMPTZ NOT NULL)""")
    op.execute("""CREATE TABLE IF NOT EXISTS government_validation_issues(id TEXT PRIMARY KEY,tenant_id TEXT NOT NULL,run_id TEXT NOT NULL REFERENCES government_validation_runs(id),row_number INTEGER,field_code TEXT,severity TEXT NOT NULL,code TEXT NOT NULL,message TEXT NOT NULL,source_ref TEXT,state TEXT NOT NULL DEFAULT 'open',resolved_by TEXT,resolved_at TIMESTAMPTZ,created_at TIMESTAMPTZ NOT NULL)""")
    op.execute("CREATE INDEX IF NOT EXISTS ix_government_validation_issues_run ON government_validation_issues(tenant_id,run_id,severity,state)")
    op.execute("""CREATE TABLE IF NOT EXISTS government_imports(id TEXT PRIMARY KEY,tenant_id TEXT NOT NULL,layout_id TEXT NOT NULL REFERENCES government_export_layouts(id),validation_run_id TEXT NOT NULL REFERENCES government_validation_runs(id),reference_period TEXT NOT NULL,original_filename TEXT NOT NULL,state TEXT NOT NULL,row_count INTEGER NOT NULL DEFAULT 0,accepted_count INTEGER NOT NULL DEFAULT 0,rejected_count INTEGER NOT NULL DEFAULT 0,sha256 TEXT NOT NULL,storage_key TEXT NOT NULL,created_by TEXT NOT NULL,created_at TIMESTAMPTZ NOT NULL,updated_at TIMESTAMPTZ NOT NULL)""")
    op.execute("""CREATE TABLE IF NOT EXISTS government_transmissions(id TEXT PRIMARY KEY,tenant_id TEXT NOT NULL,export_id TEXT NOT NULL REFERENCES government_exports(id),connection_id TEXT REFERENCES integration_connections(id),environment TEXT NOT NULL,state TEXT NOT NULL,idempotency_key TEXT NOT NULL,attempts INTEGER NOT NULL DEFAULT 0,protocol TEXT,receipt_json JSONB,provider_status TEXT,last_error TEXT,created_by TEXT NOT NULL,created_at TIMESTAMPTZ NOT NULL,updated_at TIMESTAMPTZ NOT NULL,submitted_at TIMESTAMPTZ,completed_at TIMESTAMPTZ,UNIQUE(tenant_id,idempotency_key))""")
    op.execute("""CREATE TABLE IF NOT EXISTS government_transmission_events(id TEXT PRIMARY KEY,tenant_id TEXT NOT NULL,transmission_id TEXT NOT NULL REFERENCES government_transmissions(id),event_type TEXT NOT NULL,from_state TEXT,to_state TEXT,details_json JSONB NOT NULL DEFAULT '{}'::jsonb,actor_id TEXT NOT NULL,occurred_at TIMESTAMPTZ NOT NULL)""")
    for table in TABLES:
        op.execute(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY')
        op.execute(f'ALTER TABLE "{table}" FORCE ROW LEVEL SECURITY')
        op.execute(f'DROP POLICY IF EXISTS {table}_tenant_isolation ON "{table}"')
        op.execute(f"CREATE POLICY {table}_tenant_isolation ON \"{table}\" USING (tenant_id = current_setting('app.tenant_id', true)) WITH CHECK (tenant_id = current_setting('app.tenant_id', true))")

def downgrade():
    for table in reversed(TABLES):
        op.execute(f'DROP TABLE IF EXISTS "{table}" CASCADE')
