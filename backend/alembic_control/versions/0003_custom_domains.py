"""Ciclo de vida de domínios personalizados do Control Plane.

Revision ID: 0003_custom_domains
Revises: 0002_control_outbox_delivery
"""
from alembic import op

revision = "0003_custom_domains"
down_revision = "0002_control_outbox_delivery"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE tenant_domains ADD COLUMN IF NOT EXISTS verification_method varchar(32)")
    op.execute("ALTER TABLE tenant_domains ADD COLUMN IF NOT EXISTS verification_name varchar(253)")
    op.execute("ALTER TABLE tenant_domains ADD COLUMN IF NOT EXISTS verification_token text")
    op.execute("ALTER TABLE tenant_domains ADD COLUMN IF NOT EXISTS verification_status varchar(40) NOT NULL DEFAULT 'not_required'")
    op.execute("ALTER TABLE tenant_domains ADD COLUMN IF NOT EXISTS provider varchar(40)")
    op.execute("ALTER TABLE tenant_domains ADD COLUMN IF NOT EXISTS provider_reference text")
    op.execute("ALTER TABLE tenant_domains ADD COLUMN IF NOT EXISTS verified_at text")
    op.execute("ALTER TABLE tenant_domains ADD COLUMN IF NOT EXISTS activated_at text")
    op.execute("ALTER TABLE tenant_domains ADD COLUMN IF NOT EXISTS last_error text")
    op.execute("CREATE INDEX IF NOT EXISTS ix_tenant_domains_lifecycle ON tenant_domains(status, verification_status, certificate_status)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_tenant_domains_lifecycle")
    for column in (
        "last_error", "activated_at", "verified_at", "provider_reference", "provider",
        "verification_status", "verification_token", "verification_name", "verification_method",
    ):
        op.execute(f"ALTER TABLE tenant_domains DROP COLUMN IF EXISTS {column}")
