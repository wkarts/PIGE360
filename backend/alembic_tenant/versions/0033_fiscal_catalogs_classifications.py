"""Catálogos fiscais oficiais versionados e regras de classificação por vigência."""
from __future__ import annotations

from alembic import op

revision = "0033_fiscal_catalogs_classifications"
down_revision = "0032_fiscal_context_versioning"
branch_labels = None
depends_on = None

TABLES = (
    "fiscal_catalogs",
    "fiscal_catalog_versions",
    "fiscal_catalog_entries",
    "fiscal_classification_rules",
)

DDL = r"""
CREATE TABLE IF NOT EXISTS fiscal_catalogs (
  id TEXT PRIMARY KEY,
  tenant_id TEXT NOT NULL,
  kind TEXT NOT NULL,
  name TEXT NOT NULL,
  description TEXT,
  normalization TEXT NOT NULL DEFAULT 'upper_alnum',
  code_pattern TEXT,
  metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  state TEXT NOT NULL DEFAULT 'active',
  active_version_id TEXT,
  latest_version_number INTEGER NOT NULL DEFAULT 0,
  version INTEGER NOT NULL DEFAULT 1,
  created_by TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL,
  updated_at TIMESTAMPTZ NOT NULL,
  CONSTRAINT ck_fiscal_catalog_kind CHECK (kind IN ('NCM','NBS','LC116','CFOP','CEST','CST','CSOSN','CST_IBS_CBS','CCLASSTRIB','CBENEF')),
  CONSTRAINT ck_fiscal_catalog_normalization CHECK (normalization IN ('digits','upper_alnum','preserve')),
  CONSTRAINT ck_fiscal_catalog_state CHECK (state IN ('active','inactive','archived')),
  UNIQUE(tenant_id,kind)
);
CREATE TABLE IF NOT EXISTS fiscal_catalog_versions (
  id TEXT PRIMARY KEY,
  tenant_id TEXT NOT NULL,
  fiscal_catalog_id TEXT NOT NULL REFERENCES fiscal_catalogs(id),
  version_number INTEGER NOT NULL,
  version_label TEXT NOT NULL,
  valid_from DATE NOT NULL,
  valid_until DATE,
  source_name TEXT NOT NULL,
  source_reference TEXT,
  source_sha256 TEXT NOT NULL,
  schema_version TEXT,
  notes TEXT,
  state TEXT NOT NULL DEFAULT 'draft',
  published_at TIMESTAMPTZ,
  published_by TEXT,
  entries_count INTEGER NOT NULL DEFAULT 0,
  version INTEGER NOT NULL DEFAULT 1,
  created_by TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL,
  updated_at TIMESTAMPTZ NOT NULL,
  CONSTRAINT ck_fiscal_catalog_version_period CHECK (valid_until IS NULL OR valid_until >= valid_from),
  CONSTRAINT ck_fiscal_catalog_version_sha CHECK (source_sha256 ~ '^[a-fA-F0-9]{64}$'),
  CONSTRAINT ck_fiscal_catalog_version_state CHECK (state IN ('draft','scheduled','published','superseded','archived')),
  UNIQUE(tenant_id,fiscal_catalog_id,version_number)
);
CREATE TABLE IF NOT EXISTS fiscal_catalog_entries (
  id TEXT PRIMARY KEY,
  tenant_id TEXT NOT NULL,
  fiscal_catalog_version_id TEXT NOT NULL REFERENCES fiscal_catalog_versions(id),
  code TEXT NOT NULL,
  description TEXT NOT NULL,
  parent_code TEXT,
  metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL,
  UNIQUE(tenant_id,fiscal_catalog_version_id,code)
);
CREATE TABLE IF NOT EXISTS fiscal_classification_rules (
  id TEXT PRIMARY KEY,
  tenant_id TEXT NOT NULL,
  fiscal_context_id TEXT NOT NULL REFERENCES fiscal_contexts(id),
  establishment_code TEXT,
  item_kind TEXT NOT NULL,
  item_id TEXT,
  operation_type TEXT NOT NULL,
  valid_from DATE NOT NULL,
  valid_until DATE,
  priority INTEGER NOT NULL DEFAULT 100,
  ncm TEXT,
  nbs TEXT,
  lc116 TEXT,
  cfop TEXT,
  cest TEXT,
  cst TEXT,
  csosn TEXT,
  cst_ibs_cbs TEXT,
  cclasstrib TEXT,
  cbenef TEXT,
  municipal_code TEXT,
  cnae TEXT,
  tax_configuration_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  notes TEXT,
  state TEXT NOT NULL DEFAULT 'draft',
  published_at TIMESTAMPTZ,
  published_by TEXT,
  version INTEGER NOT NULL DEFAULT 1,
  created_by TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL,
  updated_at TIMESTAMPTZ NOT NULL,
  CONSTRAINT ck_fiscal_classification_period CHECK (valid_until IS NULL OR valid_until >= valid_from),
  CONSTRAINT ck_fiscal_classification_item_kind CHECK (item_kind IN ('product','service','mixed')),
  CONSTRAINT ck_fiscal_classification_state CHECK (state IN ('draft','published','archived'))
);
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='fk_fiscal_catalog_active_version') THEN
    ALTER TABLE fiscal_catalogs ADD CONSTRAINT fk_fiscal_catalog_active_version
      FOREIGN KEY(active_version_id) REFERENCES fiscal_catalog_versions(id);
  END IF;
END $$;
CREATE INDEX IF NOT EXISTS ix_fiscal_catalog_versions_effective ON fiscal_catalog_versions(tenant_id,fiscal_catalog_id,state,valid_from,valid_until);
CREATE INDEX IF NOT EXISTS ix_fiscal_catalog_entries_code ON fiscal_catalog_entries(tenant_id,fiscal_catalog_version_id,code);
CREATE INDEX IF NOT EXISTS ix_fiscal_classification_rules_resolution ON fiscal_classification_rules(tenant_id,fiscal_context_id,item_kind,operation_type,state,valid_from,valid_until,priority);
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
