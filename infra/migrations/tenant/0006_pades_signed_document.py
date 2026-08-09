"""PAdES embedded signed-document revision fields.

Revision ID: 0006_pades_signed_document
Revises: 0005_contract_lifecycle
"""
from alembic import op

revision = "0006_pades_signed_document"
down_revision = "0005_contract_lifecycle"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for table in ("legal_contracts", "contract_versions"):
        op.execute(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS signed_document_sha256 TEXT")
        op.execute(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS signed_document_storage_key TEXT")
        op.execute(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS signature_profile TEXT")


def downgrade() -> None:
    for table in ("contract_versions", "legal_contracts"):
        op.execute(f"ALTER TABLE {table} DROP COLUMN IF EXISTS signature_profile")
        op.execute(f"ALTER TABLE {table} DROP COLUMN IF EXISTS signed_document_storage_key")
        op.execute(f"ALTER TABLE {table} DROP COLUMN IF EXISTS signed_document_sha256")
