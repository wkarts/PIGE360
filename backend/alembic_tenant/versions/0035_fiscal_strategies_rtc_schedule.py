"""Estratégias tributárias específicas e cronograma RTC versionado."""
from alembic import op
revision="0035_fiscal_strategies_rtc_schedule";down_revision="0034_fiscal_tax_calculation_engine";branch_labels=None;depends_on=None
TABLES=("fiscal_legal_source_artifacts","fiscal_strategy_rules","fiscal_rtc_schedules")
DDL=r"""
CREATE TABLE IF NOT EXISTS fiscal_legal_source_artifacts(id TEXT PRIMARY KEY,tenant_id TEXT NOT NULL,kind TEXT NOT NULL,title TEXT NOT NULL,version_label TEXT NOT NULL,valid_from DATE NOT NULL,valid_until DATE,source_reference TEXT,source_sha256 TEXT NOT NULL,metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,state TEXT NOT NULL DEFAULT 'published',created_by TEXT NOT NULL,created_at TIMESTAMPTZ NOT NULL);
CREATE TABLE IF NOT EXISTS fiscal_strategy_rules(id TEXT PRIMARY KEY,tenant_id TEXT NOT NULL,fiscal_context_id TEXT NOT NULL REFERENCES fiscal_contexts(id),establishment_code TEXT,strategy_type TEXT NOT NULL,operation_type TEXT NOT NULL,tax_regime TEXT NOT NULL,rtc_mode TEXT NOT NULL,origin_uf TEXT,destination_uf TEXT,valid_from DATE NOT NULL,valid_until DATE,priority INTEGER NOT NULL DEFAULT 100,parameters_json JSONB NOT NULL DEFAULT '{}'::jsonb,legal_source_id TEXT REFERENCES fiscal_legal_source_artifacts(id),state TEXT NOT NULL DEFAULT 'published',version INTEGER NOT NULL DEFAULT 1,created_by TEXT NOT NULL,created_at TIMESTAMPTZ NOT NULL);
CREATE INDEX IF NOT EXISTS ix_fiscal_strategy_resolution ON fiscal_strategy_rules(tenant_id,fiscal_context_id,state,valid_from,valid_until,priority);
CREATE TABLE IF NOT EXISTS fiscal_rtc_schedules(id TEXT PRIMARY KEY,tenant_id TEXT NOT NULL,fiscal_context_id TEXT NOT NULL REFERENCES fiscal_contexts(id),establishment_code TEXT,tax_regime TEXT NOT NULL,mode TEXT NOT NULL,valid_from DATE NOT NULL,valid_until DATE,legal_source_id TEXT REFERENCES fiscal_legal_source_artifacts(id),notes TEXT,state TEXT NOT NULL DEFAULT 'published',version INTEGER NOT NULL DEFAULT 1,created_by TEXT NOT NULL,created_at TIMESTAMPTZ NOT NULL);
CREATE INDEX IF NOT EXISTS ix_fiscal_rtc_resolution ON fiscal_rtc_schedules(tenant_id,fiscal_context_id,state,valid_from,valid_until);
"""
def upgrade():
 op.execute(DDL)
 for t in TABLES:
  op.execute(f'ALTER TABLE "{t}" ENABLE ROW LEVEL SECURITY');op.execute(f'ALTER TABLE "{t}" FORCE ROW LEVEL SECURITY');op.execute(f'DROP POLICY IF EXISTS {t}_tenant_isolation ON "{t}"');op.execute(f"CREATE POLICY {t}_tenant_isolation ON \"{t}\" USING (tenant_id = current_setting('app.tenant_id', true)) WITH CHECK (tenant_id = current_setting('app.tenant_id', true))")
def downgrade():
 for t in reversed(TABLES):op.execute(f'DROP TABLE IF EXISTS "{t}" CASCADE')
