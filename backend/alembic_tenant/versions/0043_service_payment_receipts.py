"""Create auditable payment receipts for service orders.

Revision ID: 0043_service_payment_receipts
Revises: 0042_service_fiscal_document_linkage
"""
from alembic import op


revision = "0043_service_payment_receipts"
down_revision = "0042_service_fiscal_document_linkage"
branch_labels = None
depends_on = None

DDL = """
CREATE TABLE IF NOT EXISTS service_receipts (
 id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, receipt_number TEXT NOT NULL,
 service_order_id TEXT NOT NULL REFERENCES service_orders(id), charge_id TEXT NOT NULL REFERENCES charges(id),
 payment_id TEXT NOT NULL REFERENCES payments(id), currency TEXT NOT NULL DEFAULT 'BRL', amount NUMERIC NOT NULL,
 payment_method TEXT NOT NULL, external_reference TEXT, recipient_name TEXT, recipient_document TEXT,
 state TEXT NOT NULL DEFAULT 'issued', document_storage_key TEXT NOT NULL, document_sha256 TEXT NOT NULL,
 snapshot_json JSONB NOT NULL DEFAULT '{}'::jsonb, issued_at TIMESTAMPTZ NOT NULL, issued_by TEXT NOT NULL,
 voided_at TIMESTAMPTZ, voided_by TEXT, void_reason TEXT, created_at TIMESTAMPTZ NOT NULL, updated_at TIMESTAMPTZ NOT NULL,
 UNIQUE(tenant_id, receipt_number)
);
CREATE INDEX IF NOT EXISTS ix_service_receipts_order ON service_receipts(tenant_id,service_order_id,state,issued_at);
CREATE INDEX IF NOT EXISTS ix_service_receipts_payment ON service_receipts(tenant_id,payment_id,state,issued_at);
CREATE UNIQUE INDEX IF NOT EXISTS ux_service_receipts_active_payment ON service_receipts(tenant_id,service_order_id,payment_id) WHERE state='issued';
"""


def upgrade() -> None:
    op.execute(DDL)
    op.execute("ALTER TABLE service_receipts ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE service_receipts FORCE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY service_receipts_tenant_isolation ON service_receipts "
        "USING (tenant_id = current_setting('app.tenant_id', true)) "
        "WITH CHECK (tenant_id = current_setting('app.tenant_id', true))"
    )


def downgrade() -> None:
    # Recibos são documentos financeiros auditáveis; o rollback lógico preserva o histórico.
    op.execute("DROP INDEX IF EXISTS ux_service_receipts_active_payment")
    op.execute("DROP INDEX IF EXISTS ix_service_receipts_payment")
    op.execute("DROP INDEX IF EXISTS ix_service_receipts_order")
