"""Ciclo de vida de documentos fiscais, providers condicionais e artefatos."""
from __future__ import annotations

from alembic import op

revision = "0038_fiscal_document_lifecycle"
down_revision = "0037_fiscal_catalog_governance_imports"
branch_labels = None
depends_on = None

TABLES = (
    "fiscal_certificate_metadata",
    "fiscal_provider_configurations",
    "fiscal_document_attempts",
    "fiscal_document_artifacts",
    "fiscal_inutilization_requests",
    "fiscal_provider_event_requests",
)

DDL = r"""
ALTER TABLE fiscal_documents ADD COLUMN IF NOT EXISTS replacement_of_document_id TEXT;
ALTER TABLE fiscal_documents ADD COLUMN IF NOT EXISTS substituted_by_document_id TEXT;
ALTER TABLE fiscal_documents ADD COLUMN IF NOT EXISTS contingency_mode TEXT;
ALTER TABLE fiscal_documents ADD COLUMN IF NOT EXISTS authorized_at TIMESTAMPTZ;
ALTER TABLE fiscal_documents ADD COLUMN IF NOT EXISTS cancelled_at TIMESTAMPTZ;

CREATE TABLE IF NOT EXISTS fiscal_certificate_metadata (
  id TEXT PRIMARY KEY,
  tenant_id TEXT NOT NULL,
  certificate_type TEXT NOT NULL DEFAULT 'a1',
  subject_name TEXT NOT NULL,
  subject_document TEXT,
  serial_number TEXT NOT NULL,
  issuer_name TEXT NOT NULL,
  valid_from TIMESTAMPTZ NOT NULL,
  valid_until TIMESTAMPTZ NOT NULL,
  fingerprint_sha256 TEXT NOT NULL,
  secret_ref TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'active',
  metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL,
  updated_at TIMESTAMPTZ NOT NULL,
  CONSTRAINT ck_fiscal_certificate_type CHECK (certificate_type IN ('a1')),
  CONSTRAINT ck_fiscal_certificate_status CHECK (status IN ('active','expired','revoked','disabled')),
  CONSTRAINT ck_fiscal_certificate_fingerprint CHECK (fingerprint_sha256 ~ '^[a-fA-F0-9]{64}$'),
  UNIQUE(tenant_id,fingerprint_sha256)
);

CREATE TABLE IF NOT EXISTS fiscal_provider_configurations (
  id TEXT PRIMARY KEY,
  tenant_id TEXT NOT NULL,
  provider_code TEXT NOT NULL,
  display_name TEXT NOT NULL,
  document_type TEXT NOT NULL,
  environment TEXT NOT NULL DEFAULT 'homologation',
  endpoint_url TEXT,
  secret_ref TEXT,
  certificate_metadata_id TEXT REFERENCES fiscal_certificate_metadata(id),
  capabilities_json JSONB NOT NULL DEFAULT '[]'::jsonb,
  settings_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  enabled BOOLEAN NOT NULL DEFAULT FALSE,
  status TEXT NOT NULL DEFAULT 'not_configured',
  last_health_status TEXT NOT NULL DEFAULT 'not_checked',
  last_health_at TIMESTAMPTZ,
  last_health_detail TEXT,
  webhook_tolerance_seconds INTEGER NOT NULL DEFAULT 300,
  version INTEGER NOT NULL DEFAULT 1,
  created_at TIMESTAMPTZ NOT NULL,
  updated_at TIMESTAMPTZ NOT NULL,
  CONSTRAINT ck_fiscal_provider_code CHECK (provider_code IN ('SefazNfeProvider','SefazNfceProvider','NationalNfseProvider','MunicipalNfseProvider','ThirdPartyFiscalProvider')),
  CONSTRAINT ck_fiscal_provider_document CHECK (document_type IN ('NF-e','NFC-e','NFS-e')),
  CONSTRAINT ck_fiscal_provider_environment CHECK (environment IN ('homologation','production')),
  CONSTRAINT ck_fiscal_provider_status CHECK (status IN ('not_configured','configured','degraded','disabled','expired_certificate')),
  UNIQUE(tenant_id,provider_code,document_type,environment)
);

CREATE TABLE IF NOT EXISTS fiscal_document_attempts (
  id TEXT PRIMARY KEY,
  tenant_id TEXT NOT NULL,
  fiscal_document_id TEXT NOT NULL REFERENCES fiscal_documents(id),
  provider_connection_id TEXT,
  operation TEXT NOT NULL,
  attempt_number INTEGER NOT NULL,
  state TEXT NOT NULL,
  request_sha256 TEXT NOT NULL,
  request_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  response_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  error_code TEXT,
  retryable BOOLEAN NOT NULL DEFAULT FALSE,
  started_at TIMESTAMPTZ NOT NULL,
  finished_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL,
  CONSTRAINT ck_fiscal_attempt_operation CHECK (operation IN ('issue','query','cancel','substitute','provider_event')),
  CONSTRAINT ck_fiscal_attempt_state CHECK (state IN ('started','completed','failed','not_configured')),
  CONSTRAINT ck_fiscal_attempt_sha CHECK (request_sha256 ~ '^[a-fA-F0-9]{64}$'),
  UNIQUE(tenant_id,fiscal_document_id,operation,attempt_number)
);

CREATE TABLE IF NOT EXISTS fiscal_document_artifacts (
  id TEXT PRIMARY KEY,
  tenant_id TEXT NOT NULL,
  fiscal_document_id TEXT NOT NULL REFERENCES fiscal_documents(id),
  artifact_type TEXT NOT NULL,
  content_type TEXT NOT NULL,
  storage_key TEXT NOT NULL,
  sha256 TEXT NOT NULL,
  bytes_count BIGINT NOT NULL,
  provider_event_id TEXT,
  created_at TIMESTAMPTZ NOT NULL,
  CONSTRAINT ck_fiscal_artifact_sha CHECK (sha256 ~ '^[a-fA-F0-9]{64}$'),
  UNIQUE(tenant_id,fiscal_document_id,artifact_type,sha256)
);

CREATE TABLE IF NOT EXISTS fiscal_inutilization_requests (
  id TEXT PRIMARY KEY,
  tenant_id TEXT NOT NULL,
  fiscal_profile_id TEXT NOT NULL,
  provider_configuration_id TEXT NOT NULL REFERENCES fiscal_provider_configurations(id),
  document_type TEXT NOT NULL,
  environment TEXT NOT NULL,
  year INTEGER NOT NULL,
  series TEXT NOT NULL,
  start_number INTEGER NOT NULL,
  end_number INTEGER NOT NULL,
  reason TEXT NOT NULL,
  state TEXT NOT NULL,
  provider_status TEXT NOT NULL,
  protocol TEXT,
  provider_request_id TEXT,
  attempts INTEGER NOT NULL DEFAULT 0,
  error_code TEXT,
  error_message TEXT,
  created_by TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL,
  updated_at TIMESTAMPTZ NOT NULL,
  CONSTRAINT ck_fiscal_inutilization_document CHECK (document_type IN ('NF-e','NFC-e')),
  CONSTRAINT ck_fiscal_inutilization_environment CHECK (environment IN ('homologation','production')),
  CONSTRAINT ck_fiscal_inutilization_interval CHECK (start_number > 0 AND end_number >= start_number),
  CONSTRAINT ck_fiscal_inutilization_state CHECK (state IN ('requested','awaiting_provider_configuration','processing','authorized','rejected')),
  UNIQUE(tenant_id,document_type,environment,year,series,start_number,end_number)
);

CREATE TABLE IF NOT EXISTS fiscal_provider_event_requests (
  id TEXT PRIMARY KEY,
  tenant_id TEXT NOT NULL,
  fiscal_document_id TEXT NOT NULL REFERENCES fiscal_documents(id),
  event_type TEXT NOT NULL,
  payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  reason TEXT NOT NULL,
  state TEXT NOT NULL,
  provider_status TEXT NOT NULL,
  protocol TEXT,
  provider_event_id TEXT,
  attempts INTEGER NOT NULL DEFAULT 0,
  error_code TEXT,
  error_message TEXT,
  created_by TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL,
  updated_at TIMESTAMPTZ NOT NULL,
  CONSTRAINT ck_fiscal_provider_event_type CHECK (event_type IN ('correction_letter','manifestation','other')),
  CONSTRAINT ck_fiscal_provider_event_state CHECK (state IN ('requested','processing','authorized','rejected'))
);

CREATE INDEX IF NOT EXISTS ix_fiscal_provider_config_status ON fiscal_provider_configurations(tenant_id,document_type,environment,status);
CREATE INDEX IF NOT EXISTS ix_fiscal_attempt_document ON fiscal_document_attempts(tenant_id,fiscal_document_id,operation,created_at);
CREATE INDEX IF NOT EXISTS ix_fiscal_artifact_document ON fiscal_document_artifacts(tenant_id,fiscal_document_id,artifact_type,created_at);
CREATE INDEX IF NOT EXISTS ix_fiscal_inutilization_status ON fiscal_inutilization_requests(tenant_id,state,created_at);
CREATE INDEX IF NOT EXISTS ix_fiscal_provider_event_status ON fiscal_provider_event_requests(tenant_id,fiscal_document_id,state,created_at);
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
    # Colunas adicionais de fiscal_documents são monotônicas: removê-las poderia
    # destruir a cadeia histórica de substituições e contingência já registrada.
