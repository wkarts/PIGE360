"""Governança e importação local dos catálogos fiscais oficiais."""
from __future__ import annotations

from alembic import op

revision = "0037_fiscal_catalog_governance_imports"
down_revision = "0036_ibpt_operational_resilience"
branch_labels = None
depends_on = None

TABLES = (
    "fiscal_catalog_source_profiles",
    "fiscal_catalog_import_runs",
    "fiscal_catalog_quarantine",
)

DDL = r"""
ALTER TABLE fiscal_catalogs DROP CONSTRAINT IF EXISTS ck_fiscal_catalog_kind;
ALTER TABLE fiscal_catalogs ADD CONSTRAINT ck_fiscal_catalog_kind CHECK (
  kind IN ('NCM','NBS','LC116','CFOP','CEST','CST','CSOSN','CST_IBS_CBS','CCLASSTRIB','CBENEF','CREDITO_PRESUMIDO','RTC_TABLE')
);

CREATE TABLE IF NOT EXISTS fiscal_catalog_source_profiles (
  id TEXT PRIMARY KEY,
  tenant_id TEXT NOT NULL,
  fiscal_catalog_id TEXT NOT NULL REFERENCES fiscal_catalogs(id),
  provider_type TEXT NOT NULL,
  provider_key TEXT NOT NULL,
  provider_version TEXT NOT NULL,
  import_format TEXT NOT NULL,
  source_reference TEXT,
  encoding TEXT NOT NULL DEFAULT 'utf-8',
  delimiter TEXT NOT NULL DEFAULT ';',
  max_age_days INTEGER NOT NULL DEFAULT 90,
  mapping_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  schema_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  state TEXT NOT NULL DEFAULT 'ready',
  last_import_at TIMESTAMPTZ,
  last_success_at TIMESTAMPTZ,
  last_error TEXT,
  version INTEGER NOT NULL DEFAULT 1,
  notes TEXT,
  created_by TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL,
  updated_at TIMESTAMPTZ NOT NULL,
  CONSTRAINT ck_fiscal_catalog_source_provider CHECK (provider_type IN ('local_file','external_http','manual_snapshot')),
  CONSTRAINT ck_fiscal_catalog_source_format CHECK (import_format IN ('csv','json','xsd')),
  CONSTRAINT ck_fiscal_catalog_source_state CHECK (state IN ('ready','not_configured','disabled','error')),
  CONSTRAINT ck_fiscal_catalog_source_max_age CHECK (max_age_days > 0),
  UNIQUE(tenant_id,fiscal_catalog_id,provider_key,provider_version)
);

CREATE TABLE IF NOT EXISTS fiscal_catalog_import_runs (
  id TEXT PRIMARY KEY,
  tenant_id TEXT NOT NULL,
  fiscal_catalog_id TEXT NOT NULL REFERENCES fiscal_catalogs(id),
  source_profile_id TEXT NOT NULL REFERENCES fiscal_catalog_source_profiles(id),
  provider_key TEXT NOT NULL,
  provider_version TEXT NOT NULL,
  import_format TEXT NOT NULL,
  original_filename TEXT NOT NULL,
  source_sha256 TEXT NOT NULL,
  storage_key TEXT NOT NULL,
  bytes_count BIGINT NOT NULL,
  state TEXT NOT NULL,
  version_label TEXT NOT NULL,
  valid_from DATE NOT NULL,
  valid_until DATE,
  schema_version TEXT,
  entries_count INTEGER NOT NULL DEFAULT 0,
  diff_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  catalog_version_id TEXT REFERENCES fiscal_catalog_versions(id),
  error_code TEXT,
  error_detail TEXT,
  idempotency_key TEXT,
  requested_by TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL,
  updated_at TIMESTAMPTZ NOT NULL,
  completed_at TIMESTAMPTZ,
  CONSTRAINT ck_fiscal_catalog_import_sha CHECK (source_sha256 ~ '^[a-fA-F0-9]{64}$'),
  CONSTRAINT ck_fiscal_catalog_import_state CHECK (state IN ('received','validated','draft_created','scheduled','published','quarantined','failed')),
  CONSTRAINT ck_fiscal_catalog_import_period CHECK (valid_until IS NULL OR valid_until >= valid_from)
);

CREATE TABLE IF NOT EXISTS fiscal_catalog_quarantine (
  id TEXT PRIMARY KEY,
  tenant_id TEXT NOT NULL,
  import_run_id TEXT NOT NULL REFERENCES fiscal_catalog_import_runs(id),
  source_profile_id TEXT NOT NULL REFERENCES fiscal_catalog_source_profiles(id),
  fiscal_catalog_id TEXT NOT NULL REFERENCES fiscal_catalogs(id),
  reason_code TEXT NOT NULL,
  reason_detail TEXT NOT NULL,
  storage_key TEXT NOT NULL,
  source_sha256 TEXT NOT NULL,
  bytes_count BIGINT NOT NULL,
  state TEXT NOT NULL DEFAULT 'open',
  created_at TIMESTAMPTZ NOT NULL,
  resolved_at TIMESTAMPTZ,
  resolved_by TEXT,
  resolution_reason TEXT,
  CONSTRAINT ck_fiscal_catalog_quarantine_sha CHECK (source_sha256 ~ '^[a-fA-F0-9]{64}$'),
  CONSTRAINT ck_fiscal_catalog_quarantine_state CHECK (state IN ('open','resolved','discarded')),
  UNIQUE(tenant_id,import_run_id,source_sha256)
);

CREATE INDEX IF NOT EXISTS ix_fiscal_catalog_sources_catalog
  ON fiscal_catalog_source_profiles(tenant_id,fiscal_catalog_id,state,provider_key);
CREATE INDEX IF NOT EXISTS ix_fiscal_catalog_import_runs_catalog
  ON fiscal_catalog_import_runs(tenant_id,fiscal_catalog_id,state,created_at);
CREATE INDEX IF NOT EXISTS ix_fiscal_catalog_quarantine_open
  ON fiscal_catalog_quarantine(tenant_id,state,fiscal_catalog_id,created_at);
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
    # A ampliação do domínio de kind é deliberadamente monotônica para não tornar
    # downgrade destrutivo quando já existirem CREDITO_PRESUMIDO/RTC_TABLE.
