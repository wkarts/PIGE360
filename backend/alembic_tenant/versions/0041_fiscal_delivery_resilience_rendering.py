"""Fiscal delivery policy, rejection trace and local rendering support.

Revision ID: 0041_fiscal_delivery_resilience_rendering
Revises: 0040_fiscal_ibpt_transparency
"""
from alembic import op

revision = "0041_fiscal_delivery_resilience_rendering"
down_revision = "0040_fiscal_ibpt_transparency"
branch_labels = None
depends_on = None

TABLES = ("fiscal_document_delivery_policies", "fiscal_document_rejections")
DDL = """
CREATE TABLE IF NOT EXISTS fiscal_document_delivery_policies (
 id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, code TEXT NOT NULL, name TEXT NOT NULL,
 document_type TEXT NOT NULL DEFAULT 'any', provider_code TEXT, environment TEXT NOT NULL DEFAULT 'any',
 valid_from DATE NOT NULL, valid_until DATE, priority INTEGER NOT NULL DEFAULT 100,
 max_attempts INTEGER NOT NULL DEFAULT 3, base_delay_seconds INTEGER NOT NULL DEFAULT 30,
 max_delay_seconds INTEGER NOT NULL DEFAULT 1800, backoff_multiplier NUMERIC(8,4) NOT NULL DEFAULT 2,
 jitter_seconds INTEGER NOT NULL DEFAULT 0, auto_retry BOOLEAN NOT NULL DEFAULT TRUE,
 contingency_after_attempts INTEGER, contingency_mode TEXT, notes TEXT,
 state TEXT NOT NULL DEFAULT 'draft', version INTEGER NOT NULL DEFAULT 1, created_by TEXT NOT NULL,
 published_by TEXT, published_at TIMESTAMPTZ, created_at TIMESTAMPTZ NOT NULL, updated_at TIMESTAMPTZ NOT NULL,
 UNIQUE(tenant_id,code,version),
 CHECK(document_type IN ('any','NF-e','NFC-e','NFS-e')),
 CHECK(environment IN ('any','homologation','production')),
 CHECK(state IN ('draft','published','superseded','archived')),
 CHECK(contingency_mode IS NULL OR contingency_mode IN ('offline','svc','epec')),
 CHECK(valid_until IS NULL OR valid_until>=valid_from)
);
CREATE TABLE IF NOT EXISTS fiscal_document_rejections (
 id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, fiscal_document_id TEXT NOT NULL REFERENCES fiscal_documents(id),
 attempt_id TEXT REFERENCES fiscal_document_attempts(id), delivery_policy_id TEXT REFERENCES fiscal_document_delivery_policies(id),
 error_code TEXT, error_message TEXT, category TEXT NOT NULL, retryable BOOLEAN NOT NULL DEFAULT FALSE,
 provider_status TEXT NOT NULL, state TEXT NOT NULL DEFAULT 'open', next_retry_at TIMESTAMPTZ,
 explanation_json JSONB NOT NULL DEFAULT '{}'::jsonb, resolution TEXT, resolved_at TIMESTAMPTZ, created_at TIMESTAMPTZ NOT NULL,
 CHECK(state IN ('open','retry_scheduled','retry_requested','resolved'))
);
CREATE INDEX IF NOT EXISTS ix_fiscal_delivery_policy_effective ON fiscal_document_delivery_policies(tenant_id,state,document_type,environment,valid_from,valid_until,priority);
CREATE INDEX IF NOT EXISTS ix_fiscal_rejection_document ON fiscal_document_rejections(tenant_id,fiscal_document_id,state,created_at);
ALTER TABLE fiscal_documents ADD COLUMN IF NOT EXISTS delivery_policy_id TEXT REFERENCES fiscal_document_delivery_policies(id);
ALTER TABLE fiscal_documents ADD COLUMN IF NOT EXISTS retry_count INTEGER NOT NULL DEFAULT 0;
ALTER TABLE fiscal_documents ADD COLUMN IF NOT EXISTS next_retry_at TIMESTAMPTZ;
"""


def upgrade() -> None:
    op.execute(DDL)
    for table in TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(f"CREATE POLICY {table}_tenant_isolation ON {table} USING (tenant_id = current_setting('app.tenant_id', true)) WITH CHECK (tenant_id = current_setting('app.tenant_id', true))")


def downgrade() -> None:
    # Histórico no documento é deliberadamente preservado; removemos apenas agregados novos.
    for table in reversed(TABLES):
        op.execute(f"DROP TABLE IF EXISTS {table} CASCADE")
