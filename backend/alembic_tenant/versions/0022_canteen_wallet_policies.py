"""Canteen menus, student wallets, restrictions and subsidies.

Revision ID: 0022_canteen_wallet_policies
Revises: 0021_secretary_enrollment_lifecycle
"""
from alembic import op
import sqlalchemy as sa

revision = "0022_canteen_wallet_policies"
down_revision = "0021_secretary_enrollment_lifecycle"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table("canteen_locations",
        sa.Column("id",sa.Text(),primary_key=True),sa.Column("tenant_id",sa.Text(),nullable=False),sa.Column("unit_id",sa.Text()),sa.Column("code",sa.Text(),nullable=False),sa.Column("name",sa.Text(),nullable=False),sa.Column("state",sa.Text(),nullable=False,server_default="active"),sa.Column("created_at",sa.Text(),nullable=False),sa.Column("updated_at",sa.Text(),nullable=False),sa.ForeignKeyConstraint(["unit_id"],["units.id"]),sa.UniqueConstraint("tenant_id","code"))
    op.create_table("canteen_menus",
        sa.Column("id",sa.Text(),primary_key=True),sa.Column("tenant_id",sa.Text(),nullable=False),sa.Column("canteen_location_id",sa.Text(),nullable=False),sa.Column("name",sa.Text(),nullable=False),sa.Column("starts_on",sa.Text()),sa.Column("ends_on",sa.Text()),sa.Column("state",sa.Text(),nullable=False,server_default="draft"),sa.Column("version",sa.Integer(),nullable=False,server_default="1"),sa.Column("created_at",sa.Text(),nullable=False),sa.Column("updated_at",sa.Text(),nullable=False),sa.ForeignKeyConstraint(["canteen_location_id"],["canteen_locations.id"]))
    op.create_table("canteen_menu_items",
        sa.Column("id",sa.Text(),primary_key=True),sa.Column("tenant_id",sa.Text(),nullable=False),sa.Column("canteen_menu_id",sa.Text(),nullable=False),sa.Column("product_id",sa.Text(),nullable=False),sa.Column("price_override",sa.Numeric()),sa.Column("available_from",sa.Text()),sa.Column("available_until",sa.Text()),sa.Column("state",sa.Text(),nullable=False,server_default="active"),sa.Column("created_at",sa.Text(),nullable=False),sa.ForeignKeyConstraint(["canteen_menu_id"],["canteen_menus.id"]),sa.ForeignKeyConstraint(["product_id"],["products.id"]),sa.UniqueConstraint("canteen_menu_id","product_id"))
    op.create_table("student_wallets",
        sa.Column("id",sa.Text(),primary_key=True),sa.Column("tenant_id",sa.Text(),nullable=False),sa.Column("student_id",sa.Text(),nullable=False),sa.Column("balance",sa.Numeric(),nullable=False,server_default="0"),sa.Column("daily_limit",sa.Numeric()),sa.Column("weekly_limit",sa.Numeric()),sa.Column("state",sa.Text(),nullable=False,server_default="active"),sa.Column("version",sa.Integer(),nullable=False,server_default="1"),sa.Column("created_at",sa.Text(),nullable=False),sa.Column("updated_at",sa.Text(),nullable=False),sa.ForeignKeyConstraint(["student_id"],["students.id"]),sa.UniqueConstraint("tenant_id","student_id"))
    op.create_table("wallet_transactions",
        sa.Column("id",sa.Text(),primary_key=True),sa.Column("tenant_id",sa.Text(),nullable=False),sa.Column("wallet_id",sa.Text(),nullable=False),sa.Column("transaction_type",sa.Text(),nullable=False),sa.Column("amount",sa.Numeric(),nullable=False),sa.Column("balance_before",sa.Numeric(),nullable=False),sa.Column("balance_after",sa.Numeric(),nullable=False),sa.Column("reference_type",sa.Text()),sa.Column("reference_id",sa.Text()),sa.Column("reason",sa.Text()),sa.Column("created_by",sa.Text()),sa.Column("idempotency_key",sa.Text()),sa.Column("created_at",sa.Text(),nullable=False),sa.ForeignKeyConstraint(["wallet_id"],["student_wallets.id"]),sa.UniqueConstraint("tenant_id","idempotency_key"))
    op.create_table("student_food_policies",
        sa.Column("id",sa.Text(),primary_key=True),sa.Column("tenant_id",sa.Text(),nullable=False),sa.Column("student_id",sa.Text(),nullable=False),sa.Column("blocked_allergens_json",sa.Text(),nullable=False,server_default="[]"),sa.Column("blocked_product_ids_json",sa.Text(),nullable=False,server_default="[]"),sa.Column("daily_limit",sa.Numeric()),sa.Column("weekly_limit",sa.Numeric()),sa.Column("purchase_start_time",sa.Text()),sa.Column("purchase_end_time",sa.Text()),sa.Column("notes",sa.Text()),sa.Column("state",sa.Text(),nullable=False,server_default="active"),sa.Column("version",sa.Integer(),nullable=False,server_default="1"),sa.Column("created_by",sa.Text(),nullable=False),sa.Column("created_at",sa.Text(),nullable=False),sa.Column("updated_at",sa.Text(),nullable=False),sa.ForeignKeyConstraint(["student_id"],["students.id"]),sa.UniqueConstraint("tenant_id","student_id"))
    op.create_table("canteen_subsidies",
        sa.Column("id",sa.Text(),primary_key=True),sa.Column("tenant_id",sa.Text(),nullable=False),sa.Column("student_id",sa.Text(),nullable=False),sa.Column("subsidy_type",sa.Text(),nullable=False),sa.Column("amount",sa.Numeric()),sa.Column("percentage",sa.Numeric()),sa.Column("valid_from",sa.Text(),nullable=False),sa.Column("valid_until",sa.Text()),sa.Column("reason",sa.Text(),nullable=False),sa.Column("state",sa.Text(),nullable=False,server_default="active"),sa.Column("created_by",sa.Text(),nullable=False),sa.Column("created_at",sa.Text(),nullable=False),sa.Column("updated_at",sa.Text(),nullable=False),sa.ForeignKeyConstraint(["student_id"],["students.id"]))
    op.create_index("ix_wallet_transactions_wallet","wallet_transactions",["tenant_id","wallet_id","created_at"])
    op.create_index("ix_food_policy_student","student_food_policies",["tenant_id","student_id","state"])
    op.create_index("ix_canteen_menu_dates","canteen_menus",["tenant_id","canteen_location_id","state","starts_on","ends_on"])
    for table in ("canteen_locations","canteen_menus","canteen_menu_items","student_wallets","wallet_transactions","student_food_policies","canteen_subsidies"):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"DROP POLICY IF EXISTS pige360_tenant_isolation ON {table}")
        op.execute(f"CREATE POLICY pige360_tenant_isolation ON {table} USING (tenant_id = current_setting('app.tenant_id', true)) WITH CHECK (tenant_id = current_setting('app.tenant_id', true))")


def downgrade() -> None:
    for table in ("canteen_subsidies","student_food_policies","wallet_transactions","student_wallets","canteen_menu_items","canteen_menus","canteen_locations"):
        op.drop_table(table)
