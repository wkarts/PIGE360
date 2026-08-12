"""Motor tributário versionado e rastreável."""
from __future__ import annotations

from alembic import op

revision = "0034_fiscal_tax_calculation_engine"
down_revision = "0033_fiscal_catalogs_classifications"
branch_labels = None
depends_on = None

TABLES = ("fiscal_tax_rule_sets", "fiscal_tax_rule_versions", "fiscal_tax_calculations")

DDL = r"""
CREATE TABLE IF NOT EXISTS fiscal_tax_rule_sets (
  id TEXT PRIMARY KEY,
  tenant_id TEXT NOT NULL,
  fiscal_context_id TEXT NOT NULL REFERENCES fiscal_contexts(id),
  code TEXT NOT NULL,
  name TEXT NOT NULL,
  description TEXT,
  establishment_code TEXT,
  operation_type TEXT NOT NULL DEFAULT 'sale',
  item_kind TEXT NOT NULL DEFAULT 'any',
  tax_regime TEXT NOT NULL DEFAULT 'any',
  rtc_mode TEXT NOT NULL DEFAULT 'any',
  priority INTEGER NOT NULL DEFAULT 100,
  state TEXT NOT NULL DEFAULT 'active',
  active_version_id TEXT,
  latest_version_number INTEGER NOT NULL DEFAULT 0,
  version INTEGER NOT NULL DEFAULT 1,
  created_by TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL,
  updated_at TIMESTAMPTZ NOT NULL,
  CONSTRAINT ck_fiscal_tax_rule_set_item_kind CHECK (item_kind IN ('product','service','mixed','any')),
  CONSTRAINT ck_fiscal_tax_rule_set_rtc_mode CHECK (rtc_mode IN ('any','disabled','simulation_only','optional_emit','required_emit')),
  CONSTRAINT ck_fiscal_tax_rule_set_state CHECK (state IN ('active','inactive','archived')),
  UNIQUE(tenant_id,code)
);
CREATE TABLE IF NOT EXISTS fiscal_tax_rule_versions (
  id TEXT PRIMARY KEY,
  tenant_id TEXT NOT NULL,
  fiscal_tax_rule_set_id TEXT NOT NULL REFERENCES fiscal_tax_rule_sets(id),
  version_number INTEGER NOT NULL,
  version_label TEXT NOT NULL,
  valid_from DATE NOT NULL,
  valid_until DATE,
  source_name TEXT NOT NULL,
  source_reference TEXT,
  source_sha256 TEXT NOT NULL,
  legal_basis_json JSONB NOT NULL DEFAULT '[]'::jsonb,
  components_json JSONB NOT NULL DEFAULT '[]'::jsonb,
  notes TEXT,
  state TEXT NOT NULL DEFAULT 'draft',
  published_at TIMESTAMPTZ,
  published_by TEXT,
  version INTEGER NOT NULL DEFAULT 1,
  created_by TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL,
  updated_at TIMESTAMPTZ NOT NULL,
  CONSTRAINT ck_fiscal_tax_rule_version_period CHECK (valid_until IS NULL OR valid_until >= valid_from),
  CONSTRAINT ck_fiscal_tax_rule_version_sha CHECK (source_sha256 ~ '^[a-fA-F0-9]{64}$'),
  CONSTRAINT ck_fiscal_tax_rule_version_state CHECK (state IN ('draft','scheduled','published','superseded','archived')),
  UNIQUE(tenant_id,fiscal_tax_rule_set_id,version_number)
);
CREATE TABLE IF NOT EXISTS fiscal_tax_calculations (
  id TEXT PRIMARY KEY,
  tenant_id TEXT NOT NULL,
  fiscal_context_id TEXT NOT NULL REFERENCES fiscal_contexts(id),
  fiscal_context_version_id TEXT NOT NULL REFERENCES fiscal_context_versions(id),
  fiscal_tax_rule_set_id TEXT NOT NULL REFERENCES fiscal_tax_rule_sets(id),
  fiscal_tax_rule_version_id TEXT NOT NULL REFERENCES fiscal_tax_rule_versions(id),
  item_kind TEXT NOT NULL,
  item_id TEXT,
  operation_type TEXT NOT NULL,
  occurred_on DATE NOT NULL,
  input_json JSONB NOT NULL,
  result_json JSONB NOT NULL,
  snapshot_sha256 TEXT NOT NULL,
  tax_total NUMERIC(18,2) NOT NULL DEFAULT 0,
  has_divergence BOOLEAN NOT NULL DEFAULT FALSE,
  created_by TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL,
  CONSTRAINT ck_fiscal_tax_calculation_kind CHECK (item_kind IN ('product','service','mixed')),
  CONSTRAINT ck_fiscal_tax_calculation_sha CHECK (snapshot_sha256 ~ '^[a-fA-F0-9]{64}$')
);
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='fk_fiscal_tax_rule_active_version') THEN
    ALTER TABLE fiscal_tax_rule_sets ADD CONSTRAINT fk_fiscal_tax_rule_active_version
      FOREIGN KEY(active_version_id) REFERENCES fiscal_tax_rule_versions(id);
  END IF;
END $$;
CREATE INDEX IF NOT EXISTS ix_fiscal_tax_rule_sets_resolution ON fiscal_tax_rule_sets(tenant_id,fiscal_context_id,state,establishment_code,operation_type,item_kind,tax_regime,rtc_mode,priority);
CREATE INDEX IF NOT EXISTS ix_fiscal_tax_rule_versions_effective ON fiscal_tax_rule_versions(tenant_id,fiscal_tax_rule_set_id,state,valid_from,valid_until);
CREATE INDEX IF NOT EXISTS ix_fiscal_tax_calculations_lookup ON fiscal_tax_calculations(tenant_id,fiscal_context_id,occurred_on,operation_type,item_kind);
"""


def upgrade() -> None:
    op.execute(DDL)
    for table in TABLES:
        op.execute(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY')
        op.execute(f'ALTER TABLE "{table}" FORCE ROW LEVEL SECURITY')
        op.execute(f'DROP POLICY IF EXISTS {table}_tenant_isolation ON "{table}"')
        op.execute(
            f'CREATE POLICY {table}_tenant_isolation ON "{table}" '
            "USING (tenant_id = current_setting('app.tenant_id', true)) "
            "WITH CHECK (tenant_id = current_setting('app.tenant_id', true))"
        )


def downgrade() -> None:
    for table in reversed(TABLES):
        op.execute(f'DROP TABLE IF EXISTS "{table}" CASCADE')
