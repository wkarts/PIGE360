"""Fiscal provider delivery state and immutable fiscal events.

Revision ID: 0008_fiscal_provider_delivery
Revises: 0007_event_delivery
"""
from alembic import op

revision = "0008_fiscal_provider_delivery"
down_revision = "0007_event_delivery"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE fiscal_profiles ADD COLUMN IF NOT EXISTS provider_connection_id TEXT REFERENCES integration_connections(id)")
    op.execute("ALTER TABLE fiscal_documents ADD COLUMN IF NOT EXISTS provider_connection_id TEXT REFERENCES integration_connections(id)")
    op.execute("ALTER TABLE fiscal_documents ADD COLUMN IF NOT EXISTS provider_document_id TEXT")
    op.execute("ALTER TABLE fiscal_documents ADD COLUMN IF NOT EXISTS provider_status TEXT NOT NULL DEFAULT 'not_configured'")
    op.execute("ALTER TABLE fiscal_documents ADD COLUMN IF NOT EXISTS attempts INTEGER NOT NULL DEFAULT 0")
    op.execute("ALTER TABLE fiscal_documents ADD COLUMN IF NOT EXISTS last_attempt_at TEXT")
    op.execute("""CREATE TABLE IF NOT EXISTS fiscal_document_events (
        id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, fiscal_document_id TEXT NOT NULL REFERENCES fiscal_documents(id),
        event_type TEXT NOT NULL, state TEXT NOT NULL, provider_connection_id TEXT REFERENCES integration_connections(id),
        provider_event_id TEXT, payload_json TEXT NOT NULL DEFAULT '{}', xml_storage_key TEXT, xml_sha256 TEXT,
        created_at TEXT NOT NULL
    )""")
    op.execute("CREATE INDEX IF NOT EXISTS idx_fiscal_document_events_document ON fiscal_document_events(tenant_id,fiscal_document_id,created_at)")
    op.execute("ALTER TABLE fiscal_document_events ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE fiscal_document_events FORCE ROW LEVEL SECURITY")
    op.execute("DROP POLICY IF EXISTS pige360_tenant_fiscal_document_events ON fiscal_document_events")
    op.execute("CREATE POLICY pige360_tenant_fiscal_document_events ON fiscal_document_events USING (tenant_id = current_setting('app.tenant_id', true)) WITH CHECK (tenant_id = current_setting('app.tenant_id', true))")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS fiscal_document_events")
    op.execute("ALTER TABLE fiscal_documents DROP COLUMN IF EXISTS last_attempt_at")
    op.execute("ALTER TABLE fiscal_documents DROP COLUMN IF EXISTS attempts")
    op.execute("ALTER TABLE fiscal_documents DROP COLUMN IF EXISTS provider_status")
    op.execute("ALTER TABLE fiscal_documents DROP COLUMN IF EXISTS provider_document_id")
    op.execute("ALTER TABLE fiscal_documents DROP COLUMN IF EXISTS provider_connection_id")
    op.execute("ALTER TABLE fiscal_profiles DROP COLUMN IF EXISTS provider_connection_id")
