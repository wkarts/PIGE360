"""Adiciona updated_at auditável aos vínculos responsável-aluno.

Revision ID: 0002_guardian_link_audit
Revises: 0001_tenant
"""
from alembic import op

revision = "0002_guardian_link_audit"
down_revision = "0001_tenant"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE guardian_students ADD COLUMN IF NOT EXISTS updated_at TEXT")
    op.execute("UPDATE guardian_students SET updated_at=created_at WHERE updated_at IS NULL")
    op.execute("ALTER TABLE guardian_students ALTER COLUMN updated_at SET NOT NULL")


def downgrade() -> None:
    op.execute("ALTER TABLE guardian_students DROP COLUMN IF EXISTS updated_at")
