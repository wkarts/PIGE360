"""Versioned human workflows, instances, tasks and request integration."""
from __future__ import annotations
from alembic import op

revision="0015_workflows"
down_revision="0014_engagement"
branch_labels=None
depends_on=None

TABLES=("workflow_definitions","workflow_definition_versions","workflow_instances","workflow_tasks","workflow_events")


def upgrade() -> None:
    op.execute("ALTER TABLE service_requests ADD COLUMN IF NOT EXISTS workflow_instance_id TEXT")
    op.execute("""
CREATE TABLE IF NOT EXISTS workflow_definitions (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, code TEXT NOT NULL, name TEXT NOT NULL,
  aggregate_type TEXT NOT NULL, state TEXT NOT NULL DEFAULT 'draft', current_version INTEGER NOT NULL DEFAULT 1,
  created_by TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL, UNIQUE(tenant_id, code)
);
CREATE TABLE IF NOT EXISTS workflow_definition_versions (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, workflow_definition_id TEXT NOT NULL REFERENCES workflow_definitions(id),
  version INTEGER NOT NULL, steps_json TEXT NOT NULL, state TEXT NOT NULL DEFAULT 'draft', change_reason TEXT,
  created_by TEXT NOT NULL, created_at TEXT NOT NULL, UNIQUE(workflow_definition_id, version)
);
CREATE TABLE IF NOT EXISTS workflow_instances (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, workflow_definition_id TEXT NOT NULL REFERENCES workflow_definitions(id),
  definition_version INTEGER NOT NULL, aggregate_type TEXT NOT NULL, aggregate_id TEXT NOT NULL,
  state TEXT NOT NULL DEFAULT 'active', current_step_key TEXT, context_json TEXT NOT NULL DEFAULT '{}',
  started_by TEXT NOT NULL, started_at TEXT NOT NULL, completed_at TEXT, cancelled_at TEXT, version INTEGER NOT NULL DEFAULT 1
);
CREATE INDEX IF NOT EXISTS ix_workflow_instances_aggregate ON workflow_instances(tenant_id, aggregate_type, aggregate_id, started_at);
CREATE TABLE IF NOT EXISTS workflow_tasks (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, workflow_instance_id TEXT NOT NULL REFERENCES workflow_instances(id),
  step_key TEXT NOT NULL, step_name TEXT NOT NULL, task_type TEXT NOT NULL, assignee_roles_json TEXT NOT NULL DEFAULT '[]',
  assignee_user_id TEXT, state TEXT NOT NULL DEFAULT 'open', due_at TEXT, decision TEXT, comment TEXT,
  completed_by TEXT, completed_at TEXT, sla_breached_at TEXT, escalation_count INTEGER NOT NULL DEFAULT 0,
  version INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_workflow_tasks_state ON workflow_tasks(tenant_id, state, due_at, created_at);
CREATE TABLE IF NOT EXISTS workflow_events (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, workflow_instance_id TEXT NOT NULL REFERENCES workflow_instances(id),
  event_type TEXT NOT NULL, from_state TEXT, to_state TEXT, from_step_key TEXT, to_step_key TEXT,
  actor_user_id TEXT, decision TEXT, comment TEXT, payload_json TEXT NOT NULL DEFAULT '{}', occurred_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_workflow_events_instance ON workflow_events(tenant_id, workflow_instance_id, occurred_at);
""")
    for table in TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"DROP POLICY IF EXISTS pige360_tenant_isolation ON {table}")
        op.execute(f"CREATE POLICY pige360_tenant_isolation ON {table} USING (tenant_id = current_setting('app.tenant_id', true)) WITH CHECK (tenant_id = current_setting('app.tenant_id', true))")


def downgrade() -> None:
    for table in reversed(TABLES):
        op.execute(f"DROP TABLE IF EXISTS {table} CASCADE")
    op.execute("ALTER TABLE service_requests DROP COLUMN IF EXISTS workflow_instance_id")
