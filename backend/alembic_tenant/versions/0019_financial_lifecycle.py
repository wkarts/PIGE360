"""Refunds, financial renegotiation and bank reconciliation support."""
from __future__ import annotations
from alembic import op
revision="0019_financial_lifecycle"
down_revision="0018_sales_inventory_operations"
branch_labels=None
depends_on=None
TABLES=("payment_refunds","payment_refund_allocations","financial_renegotiations")
def upgrade()->None:
    op.execute("""
CREATE TABLE IF NOT EXISTS payment_refunds (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, payment_id TEXT NOT NULL REFERENCES payments(id), amount NUMERIC NOT NULL,
  method TEXT NOT NULL, reason TEXT NOT NULL, state TEXT NOT NULL DEFAULT 'confirmed', external_reference TEXT,
  created_by TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS payment_refund_allocations (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, payment_refund_id TEXT NOT NULL REFERENCES payment_refunds(id),
  installment_id TEXT NOT NULL REFERENCES installments(id), amount NUMERIC NOT NULL, created_at TEXT NOT NULL,
  UNIQUE(payment_refund_id, installment_id)
);
CREATE TABLE IF NOT EXISTS financial_renegotiations (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, original_contract_id TEXT NOT NULL REFERENCES financial_contracts(id),
  new_contract_id TEXT REFERENCES financial_contracts(id), original_open_amount NUMERIC NOT NULL, new_total_amount NUMERIC NOT NULL,
  reason TEXT NOT NULL, state TEXT NOT NULL DEFAULT 'completed', terms_json TEXT NOT NULL DEFAULT '{}',
  created_by TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_payment_refunds_payment ON payment_refunds(tenant_id,payment_id,created_at);
CREATE INDEX IF NOT EXISTS ix_renegotiations_contract ON financial_renegotiations(tenant_id,original_contract_id,created_at);
""")
    for table in TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"DROP POLICY IF EXISTS pige360_tenant_isolation ON {table}")
        op.execute(f"CREATE POLICY pige360_tenant_isolation ON {table} USING (tenant_id = current_setting('app.tenant_id', true)) WITH CHECK (tenant_id = current_setting('app.tenant_id', true))")
def downgrade()->None:
    for table in reversed(TABLES):op.execute(f"DROP TABLE IF EXISTS {table} CASCADE")
