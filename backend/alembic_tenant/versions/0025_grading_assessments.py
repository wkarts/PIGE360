"""Avaliações, notas, recuperação, resultados e fechamento pedagógico."""
from alembic import op

revision="0025_grading_assessments"
down_revision="0024_canteen_sale_location"
branch_labels=None
depends_on=None

TABLES=("grading_policies","assessments","assessment_grades","assessment_grade_events","period_results","grade_period_closures")

def upgrade():
    op.execute("""CREATE TABLE IF NOT EXISTS grading_policies (
      id TEXT PRIMARY KEY,tenant_id TEXT NOT NULL,academic_year_id TEXT NOT NULL REFERENCES academic_years(id),class_group_id TEXT REFERENCES class_groups(id),component_id TEXT REFERENCES curriculum_components(id),name TEXT NOT NULL,calculation_method TEXT NOT NULL DEFAULT 'weighted_average',max_score NUMERIC NOT NULL DEFAULT 10,passing_score NUMERIC NOT NULL DEFAULT 6,attendance_minimum NUMERIC NOT NULL DEFAULT 75,rounding_precision INTEGER NOT NULL DEFAULT 2,recovery_strategy TEXT NOT NULL DEFAULT 'replace_if_higher',settings_json JSONB NOT NULL DEFAULT '{}'::jsonb,effective_from DATE NOT NULL,effective_until DATE,state TEXT NOT NULL DEFAULT 'active',version INTEGER NOT NULL DEFAULT 1,created_by TEXT,created_at TIMESTAMPTZ NOT NULL,updated_at TIMESTAMPTZ NOT NULL)""")
    op.execute("CREATE INDEX IF NOT EXISTS ix_grading_policies_scope ON grading_policies(tenant_id,academic_year_id,class_group_id,component_id,state,effective_from)")
    op.execute("""CREATE TABLE IF NOT EXISTS assessments (
      id TEXT PRIMARY KEY,tenant_id TEXT NOT NULL,academic_period_id TEXT NOT NULL REFERENCES academic_periods(id),class_group_id TEXT NOT NULL REFERENCES class_groups(id),component_id TEXT NOT NULL REFERENCES curriculum_components(id),grading_policy_id TEXT REFERENCES grading_policies(id),title TEXT NOT NULL,assessment_type TEXT NOT NULL DEFAULT 'exam',weight NUMERIC NOT NULL DEFAULT 1,max_score NUMERIC NOT NULL DEFAULT 10,due_on DATE,state TEXT NOT NULL DEFAULT 'draft',version INTEGER NOT NULL DEFAULT 1,created_by TEXT NOT NULL,created_at TIMESTAMPTZ NOT NULL,updated_at TIMESTAMPTZ NOT NULL)""")
    op.execute("CREATE INDEX IF NOT EXISTS ix_assessments_scope ON assessments(tenant_id,academic_period_id,class_group_id,component_id,state)")
    op.execute("""CREATE TABLE IF NOT EXISTS assessment_grades (
      id TEXT PRIMARY KEY,tenant_id TEXT NOT NULL,assessment_id TEXT NOT NULL REFERENCES assessments(id),enrollment_id TEXT NOT NULL REFERENCES enrollments(id),score NUMERIC,concept TEXT,status TEXT NOT NULL DEFAULT 'graded',feedback TEXT,version INTEGER NOT NULL DEFAULT 1,graded_by TEXT NOT NULL,graded_at TIMESTAMPTZ NOT NULL,updated_at TIMESTAMPTZ NOT NULL,UNIQUE(tenant_id,assessment_id,enrollment_id))""")
    op.execute("CREATE INDEX IF NOT EXISTS ix_assessment_grades_enrollment ON assessment_grades(tenant_id,enrollment_id,assessment_id)")
    op.execute("""CREATE TABLE IF NOT EXISTS assessment_grade_events (
      id TEXT PRIMARY KEY,tenant_id TEXT NOT NULL,assessment_grade_id TEXT NOT NULL REFERENCES assessment_grades(id),event_type TEXT NOT NULL,before_json JSONB NOT NULL DEFAULT '{}'::jsonb,after_json JSONB NOT NULL DEFAULT '{}'::jsonb,reason TEXT,actor_id TEXT NOT NULL,occurred_at TIMESTAMPTZ NOT NULL)""")
    op.execute("""CREATE TABLE IF NOT EXISTS period_results (
      id TEXT PRIMARY KEY,tenant_id TEXT NOT NULL,academic_period_id TEXT NOT NULL REFERENCES academic_periods(id),class_group_id TEXT NOT NULL REFERENCES class_groups(id),component_id TEXT NOT NULL REFERENCES curriculum_components(id),enrollment_id TEXT NOT NULL REFERENCES enrollments(id),grading_policy_id TEXT NOT NULL REFERENCES grading_policies(id),average_score NUMERIC NOT NULL DEFAULT 0,recovery_score NUMERIC,final_score NUMERIC NOT NULL DEFAULT 0,attendance_percentage NUMERIC NOT NULL DEFAULT 100,outcome TEXT NOT NULL DEFAULT 'pending',state TEXT NOT NULL DEFAULT 'open',calculation_json JSONB NOT NULL DEFAULT '{}'::jsonb,version INTEGER NOT NULL DEFAULT 1,calculated_at TIMESTAMPTZ NOT NULL,closed_at TIMESTAMPTZ,closed_by TEXT,updated_at TIMESTAMPTZ NOT NULL,UNIQUE(tenant_id,academic_period_id,class_group_id,component_id,enrollment_id))""")
    op.execute("CREATE INDEX IF NOT EXISTS ix_period_results_student ON period_results(tenant_id,enrollment_id,academic_period_id,component_id)")
    op.execute("""CREATE TABLE IF NOT EXISTS grade_period_closures (
      id TEXT PRIMARY KEY,tenant_id TEXT NOT NULL,academic_period_id TEXT NOT NULL REFERENCES academic_periods(id),class_group_id TEXT NOT NULL REFERENCES class_groups(id),component_id TEXT NOT NULL REFERENCES curriculum_components(id),state TEXT NOT NULL DEFAULT 'closed',version INTEGER NOT NULL DEFAULT 1,reason TEXT NOT NULL,closed_by TEXT NOT NULL,closed_at TIMESTAMPTZ NOT NULL,reopened_by TEXT,reopened_at TIMESTAMPTZ,updated_at TIMESTAMPTZ NOT NULL,UNIQUE(tenant_id,academic_period_id,class_group_id,component_id))""")
    for table in TABLES:
        op.execute(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY')
        op.execute(f'DROP POLICY IF EXISTS {table}_tenant_isolation ON "{table}"')
        op.execute(f"CREATE POLICY {table}_tenant_isolation ON \"{table}\" USING (tenant_id = current_setting('app.tenant_id', true)) WITH CHECK (tenant_id = current_setting('app.tenant_id', true))")

def downgrade():
    for table in reversed(TABLES): op.execute(f'DROP TABLE IF EXISTS "{table}" CASCADE')
