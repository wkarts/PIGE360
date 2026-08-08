"""Operações avançadas de estoque, vendas, PDV, compras e patrimônio."""
from __future__ import annotations
from alembic import op

revision="0018_sales_inventory_operations"
down_revision="0017_personnel_timekeeping"
branch_labels=None
depends_on=None
TABLES=("stock_transfers","stock_transfer_items","inventory_counts","inventory_count_items","sale_returns","sale_return_items","sale_refunds","cash_movements","purchase_receipts","purchase_receipt_items","asset_events")

def upgrade()->None:
    op.execute("""
CREATE TABLE IF NOT EXISTS stock_transfers (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, from_warehouse TEXT NOT NULL, to_warehouse TEXT NOT NULL,
  state TEXT NOT NULL DEFAULT 'completed', reason TEXT NOT NULL, created_by TEXT NOT NULL, created_at TEXT NOT NULL, completed_at TEXT
);
CREATE TABLE IF NOT EXISTS stock_transfer_items (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, stock_transfer_id TEXT NOT NULL REFERENCES stock_transfers(id),
  product_id TEXT NOT NULL REFERENCES products(id), quantity NUMERIC NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS inventory_counts (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, warehouse TEXT NOT NULL, state TEXT NOT NULL DEFAULT 'draft',
  reason TEXT, created_by TEXT NOT NULL, approved_by TEXT, created_at TEXT NOT NULL, finalized_at TEXT
);
CREATE TABLE IF NOT EXISTS inventory_count_items (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, inventory_count_id TEXT NOT NULL REFERENCES inventory_counts(id),
  product_id TEXT NOT NULL REFERENCES products(id), expected_quantity NUMERIC NOT NULL, counted_quantity NUMERIC NOT NULL,
  difference NUMERIC NOT NULL, movement_id TEXT, created_at TEXT NOT NULL, UNIQUE(inventory_count_id, product_id)
);
CREATE TABLE IF NOT EXISTS sale_returns (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, sale_id TEXT NOT NULL REFERENCES sales(id), total_amount NUMERIC NOT NULL,
  refund_method TEXT NOT NULL, state TEXT NOT NULL DEFAULT 'completed', reason TEXT NOT NULL, created_by TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS sale_return_items (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, sale_return_id TEXT NOT NULL REFERENCES sale_returns(id),
  sale_item_id TEXT NOT NULL REFERENCES sale_items(id), product_id TEXT NOT NULL REFERENCES products(id), quantity NUMERIC NOT NULL,
  amount NUMERIC NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS sale_refunds (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, sale_return_id TEXT NOT NULL REFERENCES sale_returns(id),
  method TEXT NOT NULL, amount NUMERIC NOT NULL, state TEXT NOT NULL, external_reference TEXT, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS cash_movements (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, cash_session_id TEXT NOT NULL REFERENCES cash_sessions(id),
  movement_type TEXT NOT NULL, amount NUMERIC NOT NULL, reason TEXT NOT NULL, created_by TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS purchase_receipts (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, purchase_order_id TEXT NOT NULL REFERENCES purchase_orders(id),
  state TEXT NOT NULL DEFAULT 'received', reason TEXT NOT NULL, created_by TEXT NOT NULL, received_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS purchase_receipt_items (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, purchase_receipt_id TEXT NOT NULL REFERENCES purchase_receipts(id),
  purchase_order_item_id TEXT NOT NULL REFERENCES purchase_order_items(id), product_id TEXT NOT NULL REFERENCES products(id),
  quantity NUMERIC NOT NULL, unit_cost NUMERIC NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS asset_events (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, asset_id TEXT NOT NULL REFERENCES assets(id), event_type TEXT NOT NULL,
  from_location TEXT, to_location TEXT, responsible_person_id TEXT REFERENCES people(id), cost NUMERIC, notes TEXT,
  state TEXT NOT NULL DEFAULT 'completed', occurred_at TEXT NOT NULL, created_by TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_stock_movements_product_time ON stock_movements(tenant_id,product_id,occurred_at);
CREATE INDEX IF NOT EXISTS ix_sale_returns_sale ON sale_returns(tenant_id,sale_id,created_at);
CREATE INDEX IF NOT EXISTS ix_asset_events_asset ON asset_events(tenant_id,asset_id,occurred_at);
""")
    for table in TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"DROP POLICY IF EXISTS pige360_tenant_isolation ON {table}")
        op.execute(f"CREATE POLICY pige360_tenant_isolation ON {table} USING (tenant_id = current_setting('app.tenant_id', true)) WITH CHECK (tenant_id = current_setting('app.tenant_id', true))")

def downgrade()->None:
    for table in reversed(TABLES):op.execute(f"DROP TABLE IF EXISTS {table} CASCADE")
