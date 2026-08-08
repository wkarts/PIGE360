"""Delivery metadata for one-time signature challenges.

Revision ID: 0009_signature_otp_delivery
Revises: 0008_fiscal_provider_delivery
"""
from alembic import op

revision = "0009_signature_otp_delivery"
down_revision = "0008_fiscal_provider_delivery"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE signature_otp_challenges ADD COLUMN IF NOT EXISTS delivery_state TEXT NOT NULL DEFAULT 'queued'")
    op.execute("ALTER TABLE signature_otp_challenges ADD COLUMN IF NOT EXISTS delivery_provider TEXT")
    op.execute("ALTER TABLE signature_otp_challenges ADD COLUMN IF NOT EXISTS delivery_message_id TEXT")
    op.execute("ALTER TABLE signature_otp_challenges ADD COLUMN IF NOT EXISTS delivery_error_code TEXT")
    op.execute("ALTER TABLE signature_otp_challenges ADD COLUMN IF NOT EXISTS delivered_at TEXT")


def downgrade() -> None:
    op.execute("ALTER TABLE signature_otp_challenges DROP COLUMN IF EXISTS delivered_at")
    op.execute("ALTER TABLE signature_otp_challenges DROP COLUMN IF EXISTS delivery_error_code")
    op.execute("ALTER TABLE signature_otp_challenges DROP COLUMN IF EXISTS delivery_message_id")
    op.execute("ALTER TABLE signature_otp_challenges DROP COLUMN IF EXISTS delivery_provider")
    op.execute("ALTER TABLE signature_otp_challenges DROP COLUMN IF EXISTS delivery_state")
