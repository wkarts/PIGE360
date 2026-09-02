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
    op.execute("ALTER TABLE tenant_domains ADD COLUMN IF NOT EXISTS provider_validation_json text NOT NULL DEFAULT '{}'")
    op.execute("ALTER TABLE tenant_domains ADD COLUMN IF NOT EXISTS verified_at text")
    op.execute("ALTER TABLE tenant_domains ADD COLUMN IF NOT EXISTS activated_at text")
    op.execute("ALTER TABLE tenant_domains ADD COLUMN IF NOT EXISTS last_error text")

    # Depois desta revisão, inserts canônicos simples herdam o wildcard da plataforma.
    # O fluxo de domínio personalizado sempre informa explicitamente edge_acme/cloudflare_saas.
    op.execute("ALTER TABLE tenant_domains ALTER COLUMN certificate_policy SET DEFAULT 'canonical_wildcard'")
    op.execute("ALTER TABLE tenant_domains ALTER COLUMN certificate_status SET DEFAULT 'active'")
    op.execute("ALTER TABLE tenant_domains ALTER COLUMN provider SET DEFAULT 'platform_wildcard'")

    # Canônicos existentes continuam cobertos pelo wildcard. Domínios externos criados
    # antes da prova de posse obrigatória são rebaixados até nova verificação.
    op.execute("""
        UPDATE tenant_domains
           SET certificate_policy='canonical_wildcard',
               certificate_status='active',
               verification_status='not_required',
               provider='platform_wildcard',
               provider_validation_json='{}',
               activated_at=COALESCE(activated_at, created_at),
               updated_at=COALESCE(updated_at, created_at)
         WHERE is_canonical=1
    """)
    op.execute("""
        UPDATE tenant_domains
           SET status='pending_verification',
               certificate_policy='edge_acme',
               certificate_status='not_requested',
               verification_status='pending',
               provider=NULL,
               provider_reference=NULL,
               provider_validation_json='{}',
               verified_at=NULL,
               activated_at=NULL,
               last_error='Revalidação obrigatória após upgrade do ciclo de domínio personalizado.',
               updated_at=COALESCE(updated_at, created_at)
         WHERE is_canonical=0
           AND verification_name IS NULL
           AND verification_token IS NULL
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_tenant_domains_lifecycle ON tenant_domains(status, verification_status, certificate_status)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_tenant_domains_lifecycle")
    op.execute("ALTER TABLE tenant_domains ALTER COLUMN certificate_policy SET DEFAULT 'cloudflare_managed'")
    op.execute("ALTER TABLE tenant_domains ALTER COLUMN certificate_status SET DEFAULT 'not_requested'")
    for column in (
        "last_error", "activated_at", "verified_at", "provider_validation_json", "provider_reference", "provider",
        "verification_status", "verification_token", "verification_name", "verification_method",
    ):
        op.execute(f"ALTER TABLE tenant_domains DROP COLUMN IF EXISTS {column}")
