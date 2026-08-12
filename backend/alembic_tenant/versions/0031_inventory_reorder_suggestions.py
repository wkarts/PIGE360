"""Estoque mínimo e sugestões automáticas de compra."""
from __future__ import annotations

from alembic import op

revision = "0031_inventory_reorder_suggestions"
down_revision = "0030_services_procurement_assets_vertical"
branch_labels = None
depends_on = None

TABLES = (
    "inventory_reorder_policies",
    "purchase_suggestions",
)

DDL = r"""
CREATE TABLE IF NOT EXISTS inventory_reorder_policies (
  id TEXT PRIMARY KEY,
  tenant_id TEXT NOT NULL,
  product_id TEXT NOT NULL REFERENCES products(id),
  warehouse_id TEXT NOT NULL DEFAULT 'default',
  minimum_quantity NUMERIC NOT NULL,
  target_quantity NUMERIC NOT NULL,
  lead_time_days INTEGER NOT NULL DEFAULT 0,
  preferred_supplier_id TEXT REFERENCES suppliers(id),
  state TEXT NOT NULL DEFAULT 'active',
  institution_id TEXT,
  unit_id TEXT,
  version INTEGER NOT NULL DEFAULT 1,
  created_by TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL,
  updated_at TIMESTAMPTZ NOT NULL,
  UNIQUE(tenant_id,product_id,warehouse_id)
);
CREATE TABLE IF NOT EXISTS purchase_suggestions (
  id TEXT PRIMARY KEY,
  tenant_id TEXT NOT NULL,
  policy_id TEXT NOT NULL REFERENCES inventory_reorder_policies(id),
  product_id TEXT NOT NULL REFERENCES products(id),
  warehouse_id TEXT NOT NULL,
  preferred_supplier_id TEXT REFERENCES suppliers(id),
  physical_quantity NUMERIC NOT NULL DEFAULT 0,
  reserved_quantity NUMERIC NOT NULL DEFAULT 0,
  available_quantity NUMERIC NOT NULL DEFAULT 0,
  open_purchase_quantity NUMERIC NOT NULL DEFAULT 0,
  projected_quantity NUMERIC NOT NULL DEFAULT 0,
  minimum_quantity NUMERIC NOT NULL,
  target_quantity NUMERIC NOT NULL,
  suggested_quantity NUMERIC NOT NULL,
  estimated_unit_cost NUMERIC NOT NULL DEFAULT 0,
  estimated_total NUMERIC NOT NULL DEFAULT 0,
  reason TEXT NOT NULL,
  state TEXT NOT NULL DEFAULT 'open',
  requisition_id TEXT REFERENCES purchase_requisitions(id),
  generated_at TIMESTAMPTZ NOT NULL,
  generated_by TEXT NOT NULL,
  converted_at TIMESTAMPTZ,
  converted_by TEXT,
  closed_at TIMESTAMPTZ,
  closed_by TEXT,
  closure_reason TEXT,
  version INTEGER NOT NULL DEFAULT 1,
  created_at TIMESTAMPTZ NOT NULL,
  updated_at TIMESTAMPTZ NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_inventory_reorder_policies_state
  ON inventory_reorder_policies(tenant_id,state,warehouse_id,product_id);
CREATE INDEX IF NOT EXISTS ix_purchase_suggestions_state
  ON purchase_suggestions(tenant_id,state,generated_at);
CREATE UNIQUE INDEX IF NOT EXISTS uq_purchase_suggestions_open_policy
  ON purchase_suggestions(tenant_id,policy_id) WHERE state='open';
"""


def upgrade() -> None:
    op.execute(DDL)
    for table in TABLES:
        op.execute(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY')
        op.execute(f'ALTER TABLE "{table}" FORCE ROW LEVEL SECURITY')
        op.execute(f'DROP POLICY IF EXISTS {table}_tenant_isolation ON "{table}"')
        op.execute(
            f"CREATE POLICY {table}_tenant_isolation ON \"{table}\" "
            "USING (tenant_id = current_setting('app.tenant_id', true)) "
            "WITH CHECK (tenant_id = current_setting('app.tenant_id', true))"
        )


def downgrade() -> None:
    for table in reversed(TABLES):
        op.execute(f'DROP TABLE IF EXISTS "{table}" CASCADE')
