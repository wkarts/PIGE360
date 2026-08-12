"""IBPT versioned provider profile and tax transparency separation.

Revision ID: 0040_fiscal_ibpt_transparency
Revises: 0039_fiscal_document_routing_assembly
"""
from alembic import op
revision="0040_fiscal_ibpt_transparency"
down_revision="0039_fiscal_document_routing_assembly"
branch_labels=None
depends_on=None
TABLES=("fiscal_ibpt_provider_profiles","fiscal_document_tax_transparency")

def upgrade():
    op.execute("""
CREATE TABLE fiscal_ibpt_provider_profiles (
 id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, provider_code TEXT NOT NULL, mode TEXT NOT NULL, valid_from DATE NOT NULL, valid_until DATE,
 sync_enabled BOOLEAN NOT NULL DEFAULT FALSE, fallback_enabled BOOLEAN NOT NULL DEFAULT TRUE, fallback_max_age_days INTEGER NOT NULL DEFAULT 90, stale_after_days INTEGER NOT NULL DEFAULT 120,
 base_url TEXT NOT NULL, uf_path TEXT NOT NULL, notes TEXT, state TEXT NOT NULL DEFAULT 'draft', version INTEGER NOT NULL DEFAULT 1,
 created_by TEXT NOT NULL, published_by TEXT, published_at TIMESTAMPTZ, created_at TIMESTAMPTZ NOT NULL, updated_at TIMESTAMPTZ NOT NULL,
 CHECK(mode IN ('disabled','local_snapshot','remote_sync')), CHECK(state IN ('draft','published','superseded','archived')), CHECK(valid_until IS NULL OR valid_until>=valid_from)
);
CREATE INDEX ix_fiscal_ibpt_profile_effective ON fiscal_ibpt_provider_profiles(tenant_id,state,valid_from,valid_until,version);
CREATE TABLE fiscal_document_tax_transparency (
 id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, build_id TEXT NOT NULL REFERENCES fiscal_document_builds(id), fiscal_document_id TEXT REFERENCES fiscal_documents(id),
 real_taxes_json JSONB NOT NULL DEFAULT '{}'::jsonb, approximate_ibpt_json JSONB NOT NULL DEFAULT '{}'::jsonb, vtottrib NUMERIC(18,2) NOT NULL DEFAULT 0,
 ibpt_provider_profile_id TEXT REFERENCES fiscal_ibpt_provider_profiles(id), created_at TIMESTAMPTZ NOT NULL, UNIQUE(tenant_id,build_id)
);
CREATE INDEX ix_fiscal_tax_transparency_document ON fiscal_document_tax_transparency(tenant_id,fiscal_document_id,created_at);
""")
    for table in TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(f"CREATE POLICY {table}_tenant_isolation ON {table} USING (tenant_id = current_setting('app.tenant_id', true)) WITH CHECK (tenant_id = current_setting('app.tenant_id', true))")

def downgrade():
    for table in reversed(TABLES):op.execute(f"DROP TABLE IF EXISTS {table} CASCADE")
