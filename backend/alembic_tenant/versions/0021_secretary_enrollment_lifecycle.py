"""Secretary admission and enrollment lifecycle history.

Revision ID: 0021_secretary_enrollment_lifecycle
Revises: 0020_banking_reconciliation
"""
from alembic import op
import sqlalchemy as sa

revision = "0021_secretary_enrollment_lifecycle"
down_revision = "0020_banking_reconciliation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "admission_candidate_events",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("tenant_id", sa.Text(), nullable=False),
        sa.Column("candidate_id", sa.Text(), nullable=False),
        sa.Column("event_type", sa.Text(), nullable=False),
        sa.Column("from_state", sa.Text()),
        sa.Column("to_state", sa.Text()),
        sa.Column("reason", sa.Text()),
        sa.Column("payload_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("actor_id", sa.Text(), nullable=False),
        sa.Column("occurred_at", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(["candidate_id"], ["admission_candidates.id"]),
    )
    op.create_table(
        "enrollment_movements",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("tenant_id", sa.Text(), nullable=False),
        sa.Column("enrollment_id", sa.Text(), nullable=False),
        sa.Column("movement_type", sa.Text(), nullable=False),
        sa.Column("from_state", sa.Text()),
        sa.Column("to_state", sa.Text()),
        sa.Column("from_unit_id", sa.Text()),
        sa.Column("to_unit_id", sa.Text()),
        sa.Column("from_class_group_id", sa.Text()),
        sa.Column("to_class_group_id", sa.Text()),
        sa.Column("effective_on", sa.Text(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("payload_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("actor_id", sa.Text(), nullable=False),
        sa.Column("occurred_at", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(["enrollment_id"], ["enrollments.id"]),
    )
    op.create_index("ix_admission_candidate_events", "admission_candidate_events", ["tenant_id", "candidate_id", "occurred_at"])
    op.create_index("ix_enrollment_movements", "enrollment_movements", ["tenant_id", "enrollment_id", "effective_on", "occurred_at"])
    for table in ("admission_candidate_events", "enrollment_movements"):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"DROP POLICY IF EXISTS pige360_tenant_isolation ON {table}")
        op.execute(
            f"CREATE POLICY pige360_tenant_isolation ON {table} "
            "USING (tenant_id = current_setting('app.tenant_id', true)) "
            "WITH CHECK (tenant_id = current_setting('app.tenant_id', true))"
        )


def downgrade() -> None:
    op.drop_index("ix_enrollment_movements", table_name="enrollment_movements")
    op.drop_index("ix_admission_candidate_events", table_name="admission_candidate_events")
    op.drop_table("enrollment_movements")
    op.drop_table("admission_candidate_events")
