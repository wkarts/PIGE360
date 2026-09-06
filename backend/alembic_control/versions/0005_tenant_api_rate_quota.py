"""Persist per-tenant API rate quota buckets.

Revision ID: 0005_tenant_api_rate_quota
Revises: 0004_auth_session_hardening
"""
from alembic import op


revision = "0005_tenant_api_rate_quota"
down_revision = "0004_auth_session_hardening"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """CREATE TABLE IF NOT EXISTS tenant_api_rate_buckets (
               tenant_id text NOT NULL REFERENCES platform_tenants(id) ON DELETE CASCADE,
               bucket_start text NOT NULL,
               request_count integer NOT NULL CHECK (request_count >= 0),
               updated_at text NOT NULL,
               PRIMARY KEY (tenant_id, bucket_start)
           )"""
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_tenant_api_rate_buckets_updated "
        "ON tenant_api_rate_buckets(updated_at)"
    )


def downgrade() -> None:
    # Preserva os contadores durante rollback para não reabrir artificialmente
    # uma janela de abuso quando coexistirem instâncias de versões diferentes.
    op.execute("DROP INDEX IF EXISTS ix_tenant_api_rate_buckets_updated")
