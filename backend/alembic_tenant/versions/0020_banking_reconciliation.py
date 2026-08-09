"""Bank transaction reconciliation metadata.

Revision ID: 0020_banking_reconciliation
Revises: 0019_financial_lifecycle
"""
from alembic import op
import sqlalchemy as sa

revision = "0020_banking_reconciliation"
down_revision = "0019_financial_lifecycle"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("bank_transactions", sa.Column("matched_at", sa.Text(), nullable=True))
    op.add_column("bank_transactions", sa.Column("matched_by", sa.Text(), nullable=True))
    op.add_column("bank_transactions", sa.Column("reconciliation_reason", sa.Text(), nullable=True))
    op.create_index(
        "ix_bank_transactions_reconciliation",
        "bank_transactions",
        ["tenant_id", "state", "payment_id", "posted_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_bank_transactions_reconciliation", table_name="bank_transactions")
    op.drop_column("bank_transactions", "reconciliation_reason")
    op.drop_column("bank_transactions", "matched_by")
    op.drop_column("bank_transactions", "matched_at")
