"""Contexto fiscal versionado por estabelecimento, vigência e operação."""
from __future__ import annotations

from alembic import op

revision = "0032_fiscal_context_versioning"
down_revision = "0031_inventory_reorder_suggestions"
branch_labels = None
depends_on = None

TABLES = (
    "fiscal_contexts",
    "fiscal_context_versions",
    "fiscal_context_operation_scopes",
)

DDL = r"""
CREATE TABLE IF NOT EXISTS fiscal_contexts (
  id TEXT PRIMARY KEY,
  tenant_id TEXT NOT NULL,
  code TEXT NOT NULL,
  establishment_name TEXT NOT NULL,
  legal_name TEXT,
  cnpj TEXT NOT NULL,
  institution_id TEXT REFERENCES institutions(id),
  unit_id TEXT REFERENCES units(id),
  state_registration TEXT,
  municipal_registration TEXT,
  provider_connection_id TEXT REFERENCES integration_connections(id),
  metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  state TEXT NOT NULL DEFAULT 'active',
  active_version_id TEXT,
  latest_version_number INTEGER NOT NULL DEFAULT 0,
  version INTEGER NOT NULL DEFAULT 1,
  created_by TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL,
  updated_at TIMESTAMPTZ NOT NULL,
  CONSTRAINT ck_fiscal_context_state CHECK (state IN ('active','inactive','archived')),
  CONSTRAINT ck_fiscal_context_cnpj CHECK (cnpj ~ '^[0-9]{14}$'),
  UNIQUE(tenant_id,code),
  UNIQUE(tenant_id,cnpj)
);

CREATE TABLE IF NOT EXISTS fiscal_context_versions (
  id TEXT PRIMARY KEY,
  tenant_id TEXT NOT NULL,
  fiscal_context_id TEXT NOT NULL REFERENCES fiscal_contexts(id),
  version_number INTEGER NOT NULL,
  tax_regime TEXT NOT NULL,
  uf TEXT NOT NULL,
  municipality_code TEXT NOT NULL,
  valid_from DATE NOT NULL,
  valid_until DATE,
  environment TEXT NOT NULL DEFAULT 'homologation',
  rtc_mode TEXT NOT NULL DEFAULT 'simulation_only',
  layout_version TEXT,
  schema_version TEXT,
  technical_note_version TEXT,
  ruleset_version TEXT,
  configuration_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  notes TEXT,
  state TEXT NOT NULL DEFAULT 'draft',
  published_at TIMESTAMPTZ,
  published_by TEXT,
  superseded_by_version_id TEXT REFERENCES fiscal_context_versions(id),
  version INTEGER NOT NULL DEFAULT 1,
  created_by TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL,
  updated_at TIMESTAMPTZ NOT NULL,
  CONSTRAINT ck_fiscal_context_version_period CHECK (valid_until IS NULL OR valid_until >= valid_from),
  CONSTRAINT ck_fiscal_context_version_uf CHECK (uf ~ '^[A-Z]{2}$'),
  CONSTRAINT ck_fiscal_context_version_municipality CHECK (municipality_code ~ '^[0-9]{7}$'),
  CONSTRAINT ck_fiscal_context_version_environment CHECK (environment IN ('homologation','production')),
  CONSTRAINT ck_fiscal_context_version_rtc CHECK (rtc_mode IN ('disabled','simulation_only','optional_emit','required_emit')),
  CONSTRAINT ck_fiscal_context_version_state CHECK (state IN ('draft','scheduled','published','superseded','archived')),
  UNIQUE(tenant_id,fiscal_context_id,version_number)
);

CREATE TABLE IF NOT EXISTS fiscal_context_operation_scopes (
  id TEXT PRIMARY KEY,
  tenant_id TEXT NOT NULL,
  fiscal_context_version_id TEXT NOT NULL REFERENCES fiscal_context_versions(id),
  operation_type TEXT NOT NULL,
  item_kind TEXT NOT NULL DEFAULT 'any',
  recipient_scope TEXT NOT NULL DEFAULT 'any',
  document_type TEXT NOT NULL DEFAULT 'any',
  created_at TIMESTAMPTZ NOT NULL,
  CONSTRAINT ck_fiscal_context_scope_item CHECK (item_kind IN ('any','product','service','mixed')),
  CONSTRAINT ck_fiscal_context_scope_recipient CHECK (recipient_scope IN ('any','individual','company','government','foreign')),
  CONSTRAINT ck_fiscal_context_scope_document CHECK (document_type IN ('any','NF-e','NFC-e','NFS-e')),
  UNIQUE(tenant_id,fiscal_context_version_id,operation_type,item_kind,recipient_scope,document_type)
);

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'fk_fiscal_context_active_version'
  ) THEN
    ALTER TABLE fiscal_contexts
      ADD CONSTRAINT fk_fiscal_context_active_version
      FOREIGN KEY (active_version_id) REFERENCES fiscal_context_versions(id);
  END IF;
END $$;

CREATE INDEX IF NOT EXISTS ix_fiscal_contexts_scope
  ON fiscal_contexts(tenant_id,state,institution_id,unit_id,cnpj);
CREATE INDEX IF NOT EXISTS ix_fiscal_context_versions_effective
  ON fiscal_context_versions(tenant_id,fiscal_context_id,state,valid_from,valid_until);
CREATE INDEX IF NOT EXISTS ix_fiscal_context_scopes_resolution
  ON fiscal_context_operation_scopes(tenant_id,operation_type,item_kind,recipient_scope,document_type);

ALTER TABLE fiscal_documents
  ADD COLUMN IF NOT EXISTS fiscal_context_id TEXT REFERENCES fiscal_contexts(id);
ALTER TABLE fiscal_documents
  ADD COLUMN IF NOT EXISTS fiscal_context_version_id TEXT REFERENCES fiscal_context_versions(id);
ALTER TABLE fiscal_documents
  ADD COLUMN IF NOT EXISTS fiscal_context_snapshot_json JSONB NOT NULL DEFAULT '{}'::jsonb;
CREATE INDEX IF NOT EXISTS ix_fiscal_documents_context
  ON fiscal_documents(tenant_id,fiscal_context_id,fiscal_context_version_id,created_at);
"""


def upgrade() -> None:
    op.execute(DDL)
    for table in TABLES:
        op.execute(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY')
        op.execute(f'ALTER TABLE "{table}" FORCE ROW LEVEL SECURITY')
        op.execute(f'DROP POLICY IF EXISTS {table}_tenant_isolation ON "{table}"')
        op.execute(
            f"CREATE POLICY {table}_tenant_isolation ON \"{table}\" "
            "USING (tenant_id = current_setting('app.tenant_id', true)) "
            "WITH CHECK (tenant_id = current_setting('app.tenant_id', true))"
        )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_fiscal_documents_context")
    op.execute("ALTER TABLE fiscal_documents DROP COLUMN IF EXISTS fiscal_context_snapshot_json")
    op.execute("ALTER TABLE fiscal_documents DROP COLUMN IF EXISTS fiscal_context_version_id")
    op.execute("ALTER TABLE fiscal_documents DROP COLUMN IF EXISTS fiscal_context_id")
    for table in reversed(TABLES):
        op.execute(f'DROP TABLE IF EXISTS "{table}" CASCADE')
