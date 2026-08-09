"""Vincula venda de cantina ao ponto de venda/cardápio físico."""
from alembic import op
revision="0024_canteen_sale_location"
down_revision="0023_events_travel_operations"
branch_labels=None
depends_on=None

def upgrade():
    op.execute("ALTER TABLE sales ADD COLUMN IF NOT EXISTS canteen_location_id TEXT REFERENCES canteen_locations(id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_sales_canteen_location ON sales(tenant_id,canteen_location_id,created_at)")

def downgrade():
    op.execute("DROP INDEX IF EXISTS ix_sales_canteen_location")
    op.execute("ALTER TABLE sales DROP COLUMN IF EXISTS canteen_location_id")
