"""Outbox delivery metadata and consumer inbox.

Revision ID: 0007_event_delivery
Revises: 0006_pades_signed_document
"""
from alembic import op

revision = "0007_event_delivery"
down_revision = "0006_pades_signed_document"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE outbox_events ADD COLUMN IF NOT EXISTS last_error TEXT")
    op.execute("ALTER TABLE outbox_events ADD COLUMN IF NOT EXISTS next_attempt_at TEXT")
    op.execute("""CREATE TABLE IF NOT EXISTS inbox_events (
        id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, event_id TEXT NOT NULL, consumer TEXT NOT NULL,
        event_type TEXT NOT NULL, state TEXT NOT NULL DEFAULT 'processing', attempts INTEGER NOT NULL DEFAULT 1,
        last_error TEXT, result_json TEXT NOT NULL DEFAULT '{}', created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
        processed_at TEXT, UNIQUE(tenant_id,event_id,consumer)
    )""")
    op.execute("CREATE INDEX IF NOT EXISTS idx_inbox_event_consumer ON inbox_events(tenant_id,event_id,consumer)")
    op.execute("ALTER TABLE inbox_events ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE inbox_events FORCE ROW LEVEL SECURITY")
    op.execute("DROP POLICY IF EXISTS pige360_tenant_inbox_events ON inbox_events")
    op.execute("CREATE POLICY pige360_tenant_inbox_events ON inbox_events USING (tenant_id = current_setting('app.tenant_id', true)) WITH CHECK (tenant_id = current_setting('app.tenant_id', true))")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS inbox_events")
    op.execute("ALTER TABLE outbox_events DROP COLUMN IF EXISTS next_attempt_at")
    op.execute("ALTER TABLE outbox_events DROP COLUMN IF EXISTS last_error")
