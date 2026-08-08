"""Versioned notices and configurable service request forms/history."""
from __future__ import annotations
from alembic import op

revision="0014_engagement"
down_revision="0013_communication"
branch_labels=None
depends_on=None

TABLES=("notice_versions","notice_receipts","request_type_definitions","request_type_versions","service_request_events","service_request_comments")

def upgrade() -> None:
    op.execute("ALTER TABLE notices ADD COLUMN IF NOT EXISTS version INTEGER NOT NULL DEFAULT 1")
    op.execute("ALTER TABLE service_requests ADD COLUMN IF NOT EXISTS request_type_version INTEGER")
    op.execute("ALTER TABLE service_requests ADD COLUMN IF NOT EXISTS form_data_json TEXT NOT NULL DEFAULT '{}'")
    op.execute("""
CREATE TABLE IF NOT EXISTS notice_versions (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, notice_id TEXT NOT NULL REFERENCES notices(id), version INTEGER NOT NULL,
  snapshot_json TEXT NOT NULL, change_reason TEXT, created_by TEXT NOT NULL, created_at TEXT NOT NULL, UNIQUE(notice_id, version)
);
CREATE TABLE IF NOT EXISTS notice_receipts (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, notice_id TEXT NOT NULL REFERENCES notices(id), person_id TEXT NOT NULL REFERENCES people(id),
  first_seen_at TEXT, acknowledged_at TEXT, created_at TEXT NOT NULL, UNIQUE(tenant_id, notice_id, person_id)
);
CREATE TABLE IF NOT EXISTS request_type_definitions (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, code TEXT NOT NULL, name TEXT NOT NULL, department TEXT, default_sla_hours INTEGER NOT NULL DEFAULT 72,
  state TEXT NOT NULL DEFAULT 'draft', current_version INTEGER NOT NULL DEFAULT 1, created_by TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
  UNIQUE(tenant_id, code)
);
CREATE TABLE IF NOT EXISTS request_type_versions (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, request_type_id TEXT NOT NULL REFERENCES request_type_definitions(id), version INTEGER NOT NULL,
  form_schema_json TEXT NOT NULL DEFAULT '{}', workflow_json TEXT NOT NULL DEFAULT '{}', change_reason TEXT, state TEXT NOT NULL DEFAULT 'draft',
  created_by TEXT NOT NULL, created_at TEXT NOT NULL, UNIQUE(request_type_id, version)
);
CREATE TABLE IF NOT EXISTS service_request_events (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, service_request_id TEXT NOT NULL REFERENCES service_requests(id), event_type TEXT NOT NULL,
  from_state TEXT, to_state TEXT, reason TEXT, actor_user_id TEXT NOT NULL, occurred_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS service_request_comments (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, service_request_id TEXT NOT NULL REFERENCES service_requests(id), author_user_id TEXT NOT NULL,
  body TEXT NOT NULL, visibility TEXT NOT NULL DEFAULT 'requester', created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_service_request_events_request ON service_request_events(tenant_id,service_request_id,occurred_at);
CREATE INDEX IF NOT EXISTS ix_service_request_comments_request ON service_request_comments(tenant_id,service_request_id,created_at);
""")
    for table in TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"DROP POLICY IF EXISTS pige360_tenant_isolation ON {table}")
        op.execute(f"CREATE POLICY pige360_tenant_isolation ON {table} USING (tenant_id = current_setting('app.tenant_id', true)) WITH CHECK (tenant_id = current_setting('app.tenant_id', true))")

def downgrade() -> None:
    for table in reversed(TABLES):op.execute(f"DROP TABLE IF EXISTS {table} CASCADE")
    op.execute("ALTER TABLE service_requests DROP COLUMN IF EXISTS form_data_json")
    op.execute("ALTER TABLE service_requests DROP COLUMN IF EXISTS request_type_version")
    op.execute("ALTER TABLE notices DROP COLUMN IF EXISTS version")
