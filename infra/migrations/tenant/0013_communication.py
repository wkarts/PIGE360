"""Communication templates, preferences and notification delivery history."""
from __future__ import annotations

from alembic import op

revision = "0013_communication"
down_revision = "0012_reporting"
branch_labels = None
depends_on = None

TABLES = ("communication_templates","communication_template_versions","communication_preferences","notification_events")


def upgrade() -> None:
    op.execute("""
CREATE TABLE IF NOT EXISTS communication_templates (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, template_key TEXT NOT NULL, name TEXT NOT NULL,
  channel TEXT NOT NULL, state TEXT NOT NULL DEFAULT 'draft', current_version INTEGER NOT NULL DEFAULT 1,
  created_by TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL, UNIQUE(tenant_id, template_key)
);
CREATE TABLE IF NOT EXISTS communication_template_versions (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, template_id TEXT NOT NULL REFERENCES communication_templates(id),
  version INTEGER NOT NULL, subject_template TEXT, body_template TEXT NOT NULL, variables_json TEXT NOT NULL DEFAULT '[]',
  state TEXT NOT NULL DEFAULT 'draft', change_reason TEXT, created_by TEXT NOT NULL, created_at TEXT NOT NULL,
  UNIQUE(template_id, version)
);
CREATE TABLE IF NOT EXISTS communication_preferences (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, person_id TEXT NOT NULL REFERENCES people(id), channel TEXT NOT NULL,
  enabled INTEGER NOT NULL DEFAULT 1, quiet_hours_json TEXT NOT NULL DEFAULT '{}', updated_by TEXT NOT NULL, updated_at TEXT NOT NULL,
  UNIQUE(tenant_id, person_id, channel)
);
CREATE TABLE IF NOT EXISTS notification_events (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, notification_id TEXT NOT NULL REFERENCES notifications(id),
  event_type TEXT NOT NULL, state TEXT NOT NULL, provider_message_id TEXT, details_json TEXT NOT NULL DEFAULT '{}',
  occurred_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_notification_events_notification ON notification_events(tenant_id, notification_id, occurred_at);
""")
    for table in TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"DROP POLICY IF EXISTS pige360_tenant_isolation ON {table}")
        op.execute(f"CREATE POLICY pige360_tenant_isolation ON {table} USING (tenant_id = current_setting('app.tenant_id', true)) WITH CHECK (tenant_id = current_setting('app.tenant_id', true))")


def downgrade() -> None:
    for table in reversed(TABLES):
        op.execute(f"DROP TABLE IF EXISTS {table} CASCADE")
