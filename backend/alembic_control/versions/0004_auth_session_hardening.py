"""Persist login throttling and refresh-token session families.

Revision ID: 0004_auth_session_hardening
Revises: 0003_custom_domains
"""
from alembic import op


revision = "0004_auth_session_hardening"
down_revision = "0003_custom_domains"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # A coluna permanece nullable durante o rollout para permitir que uma
    # instância anterior da API conviva brevemente com a migration. O código
    # novo sempre grava family_id; linhas antigas recebem o próprio JTI.
    op.execute("ALTER TABLE refresh_tokens ADD COLUMN IF NOT EXISTS family_id text")
    op.execute("UPDATE refresh_tokens SET family_id=jti WHERE family_id IS NULL OR family_id='' ")
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_control_refresh_tokens_family "
        "ON refresh_tokens(family_id,user_id,revoked_at)"
    )
    op.execute(
        """CREATE TABLE IF NOT EXISTS auth_login_attempts (
               identifier_hash char(64) PRIMARY KEY,
               tenant_id text,
               failed_attempts integer NOT NULL CHECK (failed_attempts >= 0),
               window_started_at text NOT NULL,
               locked_until text,
               updated_at text NOT NULL
           )"""
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_control_auth_login_attempts_updated "
        "ON auth_login_attempts(updated_at)"
    )


def downgrade() -> None:
    # O estado de bloqueio/revogação é deliberadamente preservado: removê-lo
    # poderia reativar sessões ou apagar evidência operacional após rollback.
    op.execute("DROP INDEX IF EXISTS ix_control_auth_login_attempts_updated")
    op.execute("DROP INDEX IF EXISTS ix_control_refresh_tokens_family")
