"""Persist tenant login throttling and refresh-token session families.

Revision ID: 0045_auth_session_hardening
Revises: 0044_school_sales_catalog_categories
"""
from alembic import op


revision = "0045_auth_session_hardening"
down_revision = "0044_school_sales_catalog_categories"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # A coluna permanece nullable durante o rollout para permitir que uma
    # instância anterior da API conviva brevemente com a migration. O código
    # novo sempre grava family_id; linhas antigas recebem o próprio JTI.
    op.execute("ALTER TABLE refresh_tokens ADD COLUMN IF NOT EXISTS family_id text")
    op.execute("UPDATE refresh_tokens SET family_id=jti WHERE family_id IS NULL OR family_id='' ")
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_tenant_refresh_tokens_family "
        "ON refresh_tokens(tenant_id,family_id,user_id,revoked_at)"
    )
    op.execute(
        """CREATE TABLE IF NOT EXISTS auth_login_attempts (
               identifier_hash char(64) PRIMARY KEY,
               tenant_id text NOT NULL,
               failed_attempts integer NOT NULL CHECK (failed_attempts >= 0),
               window_started_at text NOT NULL,
               locked_until text,
               updated_at text NOT NULL
           )"""
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_tenant_auth_login_attempts_updated "
        "ON auth_login_attempts(tenant_id,updated_at)"
    )
    op.execute("ALTER TABLE auth_login_attempts ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE auth_login_attempts FORCE ROW LEVEL SECURITY")
    op.execute("DROP POLICY IF EXISTS pige360_tenant_auth_login_attempts ON auth_login_attempts")
    op.execute(
        """CREATE POLICY pige360_tenant_auth_login_attempts ON auth_login_attempts
           USING (tenant_id = current_setting('app.tenant_id', true))
           WITH CHECK (tenant_id = current_setting('app.tenant_id', true))"""
    )


def downgrade() -> None:
    # O estado de bloqueio/revogação é deliberadamente preservado: removê-lo
    # poderia reativar sessões ou apagar evidência operacional após rollback.
    op.execute("DROP INDEX IF EXISTS ix_tenant_auth_login_attempts_updated")
    op.execute("DROP INDEX IF EXISTS ix_tenant_refresh_tokens_family")
