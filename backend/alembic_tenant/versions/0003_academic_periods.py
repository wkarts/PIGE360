"""Períodos acadêmicos reais e compatibilidade com planos alpha.

Revision ID: 0003_academic_periods
Revises: 0002_guardian_link_audit
"""
from alembic import op

revision = "0003_academic_periods"
down_revision = "0002_guardian_link_audit"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
    CREATE TABLE IF NOT EXISTS academic_periods (
      id TEXT PRIMARY KEY,
      tenant_id TEXT NOT NULL,
      academic_year_id TEXT NOT NULL REFERENCES academic_years(id),
      name TEXT NOT NULL,
      period_type TEXT NOT NULL,
      sequence INTEGER NOT NULL DEFAULT 1,
      starts_on TEXT NOT NULL,
      ends_on TEXT NOT NULL,
      state TEXT NOT NULL DEFAULT 'active',
      version INTEGER NOT NULL DEFAULT 1,
      created_at TEXT NOT NULL,
      updated_at TEXT NOT NULL,
      UNIQUE(tenant_id, academic_year_id, period_type, sequence)
    )
    """)
    # O UUID anual igual ao UUID do ano preserva academic_period_id gravado por versões alpha.
    op.execute("""
    INSERT INTO academic_periods(id,tenant_id,academic_year_id,name,period_type,sequence,starts_on,ends_on,state,version,created_at,updated_at)
    SELECT ay.id,ay.tenant_id,ay.id,ay.name || ' — Anual','annual',1,ay.starts_on,ay.ends_on,'active',1,ay.created_at,ay.updated_at
      FROM academic_years ay
     WHERE NOT EXISTS (SELECT 1 FROM academic_periods ap WHERE ap.id=ay.id)
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_academic_periods_dates ON academic_periods(tenant_id, academic_year_id, starts_on, ends_on)")
    op.execute("ALTER TABLE academic_periods ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE academic_periods FORCE ROW LEVEL SECURITY")
    op.execute("DROP POLICY IF EXISTS pige360_tenant_academic_periods ON academic_periods")
    op.execute("CREATE POLICY pige360_tenant_academic_periods ON academic_periods USING (tenant_id = current_setting('app.tenant_id', true)) WITH CHECK (tenant_id = current_setting('app.tenant_id', true))")
    op.execute("""
    DO $$ BEGIN
      IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='fk_teaching_plans_academic_period') THEN
        ALTER TABLE teaching_plans ADD CONSTRAINT fk_teaching_plans_academic_period
          FOREIGN KEY (academic_period_id) REFERENCES academic_periods(id) NOT VALID;
      END IF;
    END $$
    """)
    op.execute("ALTER TABLE teaching_plans VALIDATE CONSTRAINT fk_teaching_plans_academic_period")


def downgrade() -> None:
    op.execute("ALTER TABLE teaching_plans DROP CONSTRAINT IF EXISTS fk_teaching_plans_academic_period")
    op.execute("DROP TABLE IF EXISTS academic_periods")
