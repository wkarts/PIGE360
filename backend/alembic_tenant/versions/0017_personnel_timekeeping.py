"""Departamento pessoal, férias, benefícios e fechamento/ajustes do ponto."""
from __future__ import annotations
from alembic import op

revision="0017_personnel_timekeeping"
down_revision="0016_student_services"
branch_labels=None
depends_on=None

TABLES=("employee_benefits","personnel_leaves","vacation_periods","timekeeping_adjustments","timekeeping_period_closures")

def upgrade() -> None:
    op.execute("""
CREATE TABLE IF NOT EXISTS employee_benefits (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, employee_id TEXT NOT NULL REFERENCES employees(id),
  benefit_type TEXT NOT NULL, provider TEXT, amount NUMERIC NOT NULL DEFAULT 0,
  starts_on TEXT NOT NULL, ends_on TEXT, state TEXT NOT NULL DEFAULT 'active', version INTEGER NOT NULL DEFAULT 1,
  metadata_json TEXT NOT NULL DEFAULT '{}', created_by TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS personnel_leaves (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, employee_id TEXT NOT NULL REFERENCES employees(id),
  leave_type TEXT NOT NULL, starts_on TEXT NOT NULL, ends_on TEXT NOT NULL, reason TEXT NOT NULL,
  deduct_payroll INTEGER NOT NULL DEFAULT 0, deduct_timekeeping INTEGER NOT NULL DEFAULT 1,
  document_id TEXT, state TEXT NOT NULL DEFAULT 'submitted', version INTEGER NOT NULL DEFAULT 1,
  requested_by TEXT NOT NULL, approved_by TEXT, approved_at TEXT, rejection_reason TEXT,
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS vacation_periods (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, employee_id TEXT NOT NULL REFERENCES employees(id),
  accrual_start TEXT NOT NULL, accrual_end TEXT NOT NULL, scheduled_start TEXT NOT NULL, scheduled_end TEXT NOT NULL,
  days INTEGER NOT NULL, state TEXT NOT NULL DEFAULT 'scheduled', version INTEGER NOT NULL DEFAULT 1,
  approved_by TEXT, approved_at TEXT, cancellation_reason TEXT, created_by TEXT NOT NULL,
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS timekeeping_adjustments (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, employee_id TEXT NOT NULL REFERENCES employees(id),
  time_entry_id TEXT REFERENCES time_entries(id), requested_event_type TEXT NOT NULL, requested_occurred_at TEXT NOT NULL,
  reason TEXT NOT NULL, state TEXT NOT NULL DEFAULT 'submitted', version INTEGER NOT NULL DEFAULT 1,
  requested_by TEXT NOT NULL, reviewed_by TEXT, reviewed_at TEXT, review_reason TEXT,
  replacement_entry_id TEXT REFERENCES time_entries(id), created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS timekeeping_period_closures (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, competence TEXT NOT NULL,
  state TEXT NOT NULL DEFAULT 'closed', version INTEGER NOT NULL DEFAULT 1,
  closed_by TEXT NOT NULL, closed_at TEXT NOT NULL, reopened_by TEXT, reopened_at TEXT, reopen_reason TEXT,
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL, UNIQUE(tenant_id, competence)
);
CREATE INDEX IF NOT EXISTS ix_personnel_leaves_employee ON personnel_leaves(tenant_id, employee_id, starts_on, ends_on, state);
CREATE INDEX IF NOT EXISTS ix_vacation_periods_employee ON vacation_periods(tenant_id, employee_id, scheduled_start, scheduled_end, state);
CREATE INDEX IF NOT EXISTS ix_timekeeping_adjustments_employee ON timekeeping_adjustments(tenant_id, employee_id, state, created_at);
""")
    for table in TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"DROP POLICY IF EXISTS pige360_tenant_isolation ON {table}")
        op.execute(f"CREATE POLICY pige360_tenant_isolation ON {table} USING (tenant_id = current_setting('app.tenant_id', true)) WITH CHECK (tenant_id = current_setting('app.tenant_id', true))")

def downgrade() -> None:
    for table in reversed(TABLES):
        op.execute(f"DROP TABLE IF EXISTS {table} CASCADE")
