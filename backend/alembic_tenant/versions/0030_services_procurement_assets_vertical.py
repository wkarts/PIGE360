"""Serviços, compras, lotes, reservas e patrimônio em fluxos verticais completos."""
from __future__ import annotations

from alembic import op

revision = "0030_services_procurement_assets_vertical"
down_revision = "0029_admissions_funnel"
branch_labels = None
depends_on = None

NEW_TABLES = (
    "service_catalogs",
    "service_variants",
    "service_fiscal_profiles",
    "service_price_tables",
    "service_billing_rules",
    "service_subscriptions",
    "service_executions",
    "service_competencies",
    "service_fiscal_events",
    "charges",
    "charge_items",
    "accounts_receivable",
    "product_variants",
    "product_barcodes",
    "supplier_contacts",
    "purchase_requisitions",
    "purchase_requisition_items",
    "requests_for_quotation",
    "quotation_items",
    "quotation_suppliers",
    "quotation_supplier_items",
    "goods_receipts",
    "goods_receipt_items",
    "inventory_lots",
    "purchase_returns",
    "purchase_return_items",
    "inventory_reservations",
    "asset_locations",
    "asset_movements",
    "asset_maintenances",
    "asset_loans",
    "asset_depreciations",
)

ALTER_COLUMNS: dict[str, tuple[str, ...]] = {
    "services": (
        "catalog_id TEXT", "service_type TEXT NOT NULL DEFAULT 'other'", "recurrence_type TEXT NOT NULL DEFAULT 'one_time'",
        "unit_of_measure TEXT NOT NULL DEFAULT 'unit'", "default_duration_minutes INTEGER", "cost_center_id TEXT",
        "taxable BOOLEAN NOT NULL DEFAULT TRUE", "metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb", "institution_id TEXT",
        "unit_id TEXT", "version INTEGER NOT NULL DEFAULT 1",
    ),
    "service_orders": (
        "order_number TEXT", "subscriber_person_id TEXT", "subscription_id TEXT", "competence_id TEXT", "cost_center_id TEXT",
        "currency TEXT NOT NULL DEFAULT 'BRL'", "subtotal NUMERIC NOT NULL DEFAULT 0", "discount_amount NUMERIC NOT NULL DEFAULT 0",
        "due_date DATE", "installment_count INTEGER NOT NULL DEFAULT 1", "charge_id TEXT", "fiscal_status TEXT NOT NULL DEFAULT 'pending'",
        "notes TEXT", "confirmed_at TIMESTAMPTZ", "confirmed_by TEXT", "started_at TIMESTAMPTZ", "completed_at TIMESTAMPTZ",
        "cancelled_at TIMESTAMPTZ", "cancellation_reason TEXT", "institution_id TEXT", "unit_id TEXT",
        "version INTEGER NOT NULL DEFAULT 1",
    ),
    "service_order_items": (
        "variant_id TEXT", "description TEXT", "discount_amount NUMERIC NOT NULL DEFAULT 0", "competence_start DATE",
        "competence_end DATE", "fiscal_profile_snapshot_json JSONB NOT NULL DEFAULT '{}'::jsonb",
        "execution_status TEXT NOT NULL DEFAULT 'pending'", "executed_quantity NUMERIC NOT NULL DEFAULT 0",
    ),
    "stock_movements": ("lot_id TEXT", "balance_after NUMERIC"),
    "suppliers": (
        "code TEXT", "rating NUMERIC", "payment_terms_json JSONB NOT NULL DEFAULT '{}'::jsonb",
        "fiscal_profile_json JSONB NOT NULL DEFAULT '{}'::jsonb", "notes TEXT", "institution_id TEXT", "unit_id TEXT",
        "version INTEGER NOT NULL DEFAULT 1",
    ),
    "purchase_orders": (
        "warehouse_id TEXT NOT NULL DEFAULT 'default'", "quotation_id TEXT", "requisition_id TEXT",
        "currency TEXT NOT NULL DEFAULT 'BRL'", "subtotal NUMERIC NOT NULL DEFAULT 0", "freight_amount NUMERIC NOT NULL DEFAULT 0",
        "discount_amount NUMERIC NOT NULL DEFAULT 0", "notes TEXT", "approved_at TIMESTAMPTZ", "approved_by TEXT",
        "closed_at TIMESTAMPTZ", "institution_id TEXT", "unit_id TEXT", "version INTEGER NOT NULL DEFAULT 1",
    ),
    "purchase_order_items": (
        "returned_quantity NUMERIC NOT NULL DEFAULT 0", "discount_amount NUMERIC NOT NULL DEFAULT 0",
        "total_amount NUMERIC NOT NULL DEFAULT 0", "fiscal_profile_snapshot_json JSONB NOT NULL DEFAULT '{}'::jsonb",
    ),
    "inventory_counts": (
        "started_at TIMESTAMPTZ", "snapshot_json JSONB NOT NULL DEFAULT '{}'::jsonb", "institution_id TEXT", "unit_id TEXT",
        "version INTEGER NOT NULL DEFAULT 1",
    ),
    "inventory_count_items": ("lot_id TEXT", "notes TEXT"),
    "assets": (
        "tag TEXT", "name TEXT", "location_id TEXT", "product_id TEXT", "receipt_item_id TEXT", "serial_number TEXT",
        "useful_life_months INTEGER", "residual_value NUMERIC NOT NULL DEFAULT 0",
        "accumulated_depreciation NUMERIC NOT NULL DEFAULT 0", "warranty_until DATE",
        "metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb", "institution_id TEXT", "unit_id TEXT",
        "version INTEGER NOT NULL DEFAULT 1",
    ),
}

DDL = r"""
CREATE TABLE IF NOT EXISTS service_catalogs(id TEXT PRIMARY KEY,tenant_id TEXT NOT NULL,code TEXT NOT NULL,name TEXT NOT NULL,description TEXT,valid_from DATE,valid_until DATE,state TEXT NOT NULL DEFAULT 'active',institution_id TEXT,unit_id TEXT,version INTEGER NOT NULL DEFAULT 1,created_at TIMESTAMPTZ NOT NULL,updated_at TIMESTAMPTZ NOT NULL,UNIQUE(tenant_id,code));
CREATE TABLE IF NOT EXISTS service_variants(id TEXT PRIMARY KEY,tenant_id TEXT NOT NULL,service_id TEXT NOT NULL REFERENCES services(id),code TEXT NOT NULL,name TEXT NOT NULL,description TEXT,duration_minutes INTEGER,capacity INTEGER,state TEXT NOT NULL DEFAULT 'active',metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,institution_id TEXT,unit_id TEXT,version INTEGER NOT NULL DEFAULT 1,created_at TIMESTAMPTZ NOT NULL,updated_at TIMESTAMPTZ NOT NULL,UNIQUE(tenant_id,service_id,code));
CREATE TABLE IF NOT EXISTS service_fiscal_profiles(id TEXT PRIMARY KEY,tenant_id TEXT NOT NULL,service_id TEXT NOT NULL REFERENCES services(id),variant_id TEXT,valid_from DATE NOT NULL,valid_until DATE,nbs_code TEXT,lc116_code TEXT,municipal_service_code TEXT,cnae_code TEXT,iss_rate NUMERIC NOT NULL DEFAULT 0,ibs_rate NUMERIC NOT NULL DEFAULT 0,cbs_rate NUMERIC NOT NULL DEFAULT 0,cclass_trib TEXT,fiscal_trigger TEXT NOT NULL DEFAULT 'billing',withholding_json JSONB NOT NULL DEFAULT '{}'::jsonb,rules_snapshot_json JSONB NOT NULL DEFAULT '{}'::jsonb,state TEXT NOT NULL DEFAULT 'draft',classification_status TEXT NOT NULL DEFAULT 'incomplete',published_at TIMESTAMPTZ,published_by TEXT,institution_id TEXT,unit_id TEXT,version INTEGER NOT NULL DEFAULT 1,created_at TIMESTAMPTZ NOT NULL,updated_at TIMESTAMPTZ NOT NULL);
CREATE TABLE IF NOT EXISTS service_price_tables(id TEXT PRIMARY KEY,tenant_id TEXT NOT NULL,service_id TEXT NOT NULL REFERENCES services(id),variant_id TEXT,name TEXT NOT NULL,valid_from DATE NOT NULL,valid_until DATE,currency TEXT NOT NULL DEFAULT 'BRL',amount NUMERIC NOT NULL,billing_frequency TEXT NOT NULL DEFAULT 'one_time',state TEXT NOT NULL DEFAULT 'active',institution_id TEXT,unit_id TEXT,version INTEGER NOT NULL DEFAULT 1,created_at TIMESTAMPTZ NOT NULL,updated_at TIMESTAMPTZ NOT NULL);
CREATE TABLE IF NOT EXISTS service_billing_rules(id TEXT PRIMARY KEY,tenant_id TEXT NOT NULL,service_id TEXT NOT NULL REFERENCES services(id),variant_id TEXT,code TEXT NOT NULL,name TEXT NOT NULL,billing_trigger TEXT NOT NULL DEFAULT 'competence',due_day INTEGER NOT NULL DEFAULT 10,installment_count INTEGER NOT NULL DEFAULT 1,interval_months INTEGER NOT NULL DEFAULT 1,recognition_policy TEXT NOT NULL DEFAULT 'competence',fiscal_trigger TEXT NOT NULL DEFAULT 'competence',proration_policy TEXT NOT NULL DEFAULT 'none',state TEXT NOT NULL DEFAULT 'active',config_json JSONB NOT NULL DEFAULT '{}'::jsonb,institution_id TEXT,unit_id TEXT,version INTEGER NOT NULL DEFAULT 1,created_at TIMESTAMPTZ NOT NULL,updated_at TIMESTAMPTZ NOT NULL,UNIQUE(tenant_id,service_id,code));
CREATE TABLE IF NOT EXISTS service_subscriptions(id TEXT PRIMARY KEY,tenant_id TEXT NOT NULL,subscription_number TEXT NOT NULL,service_id TEXT NOT NULL REFERENCES services(id),variant_id TEXT,subscriber_person_id TEXT NOT NULL REFERENCES people(id),enrollment_id TEXT REFERENCES enrollments(id),financial_contract_id TEXT REFERENCES financial_contracts(id),billing_rule_id TEXT NOT NULL REFERENCES service_billing_rules(id),starts_on DATE NOT NULL,ends_on DATE,quantity NUMERIC NOT NULL DEFAULT 1,unit_price NUMERIC NOT NULL,discount_amount NUMERIC NOT NULL DEFAULT 0,cycle_amount NUMERIC NOT NULL,next_competence_on DATE NOT NULL,auto_renew BOOLEAN NOT NULL DEFAULT FALSE,state TEXT NOT NULL DEFAULT 'draft',suspended_at TIMESTAMPTZ,cancelled_at TIMESTAMPTZ,cancellation_reason TEXT,institution_id TEXT,unit_id TEXT,version INTEGER NOT NULL DEFAULT 1,created_at TIMESTAMPTZ NOT NULL,updated_at TIMESTAMPTZ NOT NULL,UNIQUE(tenant_id,subscription_number));
CREATE TABLE IF NOT EXISTS service_executions(id TEXT PRIMARY KEY,tenant_id TEXT NOT NULL,execution_number TEXT NOT NULL,service_order_id TEXT NOT NULL REFERENCES service_orders(id),service_order_item_id TEXT NOT NULL REFERENCES service_order_items(id),subscription_id TEXT,scheduled_at TIMESTAMPTZ,started_at TIMESTAMPTZ,completed_at TIMESTAMPTZ,quantity NUMERIC NOT NULL,state TEXT NOT NULL DEFAULT 'scheduled',performer_person_id TEXT REFERENCES people(id),notes TEXT,evidence_json JSONB NOT NULL DEFAULT '{}'::jsonb,institution_id TEXT,unit_id TEXT,version INTEGER NOT NULL DEFAULT 1,created_at TIMESTAMPTZ NOT NULL,updated_at TIMESTAMPTZ NOT NULL,UNIQUE(tenant_id,execution_number));
CREATE TABLE IF NOT EXISTS service_competencies(id TEXT PRIMARY KEY,tenant_id TEXT NOT NULL,subscription_id TEXT NOT NULL REFERENCES service_subscriptions(id),competence_key TEXT NOT NULL,period_start DATE NOT NULL,period_end DATE NOT NULL,due_date DATE NOT NULL,amount NUMERIC NOT NULL,service_order_id TEXT,charge_id TEXT,state TEXT NOT NULL DEFAULT 'pending',billed_at TIMESTAMPTZ,institution_id TEXT,unit_id TEXT,version INTEGER NOT NULL DEFAULT 1,created_at TIMESTAMPTZ NOT NULL,updated_at TIMESTAMPTZ NOT NULL,UNIQUE(tenant_id,subscription_id,competence_key));
CREATE TABLE IF NOT EXISTS service_fiscal_events(id TEXT PRIMARY KEY,tenant_id TEXT NOT NULL,event_key TEXT NOT NULL,service_order_id TEXT NOT NULL REFERENCES service_orders(id),service_order_item_id TEXT,competence_id TEXT,trigger_type TEXT NOT NULL,document_type TEXT NOT NULL DEFAULT 'nfse',provider_code TEXT,state TEXT NOT NULL DEFAULT 'not_configured',payload_snapshot_json JSONB NOT NULL DEFAULT '{}'::jsonb,requested_at TIMESTAMPTZ NOT NULL,completed_at TIMESTAMPTZ,failure_code TEXT,failure_message TEXT,created_at TIMESTAMPTZ NOT NULL,updated_at TIMESTAMPTZ NOT NULL,UNIQUE(tenant_id,event_key));
CREATE TABLE IF NOT EXISTS charges(id TEXT PRIMARY KEY,tenant_id TEXT NOT NULL,charge_number TEXT NOT NULL,financial_contract_id TEXT REFERENCES financial_contracts(id),enrollment_id TEXT REFERENCES enrollments(id),responsible_person_id TEXT REFERENCES people(id),origin_type TEXT NOT NULL,origin_id TEXT NOT NULL,currency TEXT NOT NULL DEFAULT 'BRL',total_amount NUMERIC NOT NULL,paid_amount NUMERIC NOT NULL DEFAULT 0,refunded_amount NUMERIC NOT NULL DEFAULT 0,outstanding_amount NUMERIC NOT NULL,due_date DATE NOT NULL,state TEXT NOT NULL DEFAULT 'open',generated_at TIMESTAMPTZ NOT NULL,cancelled_at TIMESTAMPTZ,cancellation_reason TEXT,created_at TIMESTAMPTZ NOT NULL,updated_at TIMESTAMPTZ NOT NULL,UNIQUE(tenant_id,charge_number),UNIQUE(tenant_id,origin_type,origin_id));
CREATE TABLE IF NOT EXISTS charge_items(id TEXT PRIMARY KEY,tenant_id TEXT NOT NULL,charge_id TEXT NOT NULL REFERENCES charges(id),description TEXT NOT NULL,quantity NUMERIC NOT NULL DEFAULT 1,unit_amount NUMERIC NOT NULL,discount_amount NUMERIC NOT NULL DEFAULT 0,total_amount NUMERIC NOT NULL,accounting_code TEXT,metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,created_at TIMESTAMPTZ NOT NULL);
CREATE TABLE IF NOT EXISTS accounts_receivable(id TEXT PRIMARY KEY,tenant_id TEXT NOT NULL,receivable_number TEXT NOT NULL,installment_id TEXT REFERENCES installments(id),charge_id TEXT REFERENCES charges(id),responsible_person_id TEXT REFERENCES people(id),cost_center_id TEXT,amount NUMERIC NOT NULL,paid_amount NUMERIC NOT NULL DEFAULT 0,refunded_amount NUMERIC NOT NULL DEFAULT 0,outstanding_amount NUMERIC NOT NULL,due_date DATE NOT NULL,state TEXT NOT NULL DEFAULT 'open',created_at TIMESTAMPTZ NOT NULL,updated_at TIMESTAMPTZ NOT NULL,UNIQUE(tenant_id,receivable_number));
CREATE TABLE IF NOT EXISTS product_variants(id TEXT PRIMARY KEY,tenant_id TEXT NOT NULL,product_id TEXT NOT NULL REFERENCES products(id),sku TEXT NOT NULL,name TEXT NOT NULL,attributes_json JSONB NOT NULL DEFAULT '{}'::jsonb,sale_price NUMERIC,cost_price NUMERIC,state TEXT NOT NULL DEFAULT 'active',institution_id TEXT,unit_id TEXT,version INTEGER NOT NULL DEFAULT 1,created_at TIMESTAMPTZ NOT NULL,updated_at TIMESTAMPTZ NOT NULL,UNIQUE(tenant_id,sku));
CREATE TABLE IF NOT EXISTS product_barcodes(id TEXT PRIMARY KEY,tenant_id TEXT NOT NULL,product_id TEXT NOT NULL REFERENCES products(id),variant_id TEXT,barcode TEXT NOT NULL,barcode_type TEXT NOT NULL DEFAULT 'ean13',is_primary BOOLEAN NOT NULL DEFAULT FALSE,created_at TIMESTAMPTZ NOT NULL,UNIQUE(tenant_id,barcode));
CREATE TABLE IF NOT EXISTS supplier_contacts(id TEXT PRIMARY KEY,tenant_id TEXT NOT NULL,supplier_id TEXT NOT NULL REFERENCES suppliers(id),name TEXT NOT NULL,email TEXT,phone TEXT,role TEXT,is_primary BOOLEAN NOT NULL DEFAULT FALSE,created_at TIMESTAMPTZ NOT NULL,updated_at TIMESTAMPTZ NOT NULL);
CREATE TABLE IF NOT EXISTS purchase_requisitions(id TEXT PRIMARY KEY,tenant_id TEXT NOT NULL,requisition_number TEXT NOT NULL,requester_user_id TEXT NOT NULL,department_id TEXT,cost_center_id TEXT,needed_by DATE,justification TEXT NOT NULL,state TEXT NOT NULL DEFAULT 'draft',submitted_at TIMESTAMPTZ,submitted_by TEXT,approved_at TIMESTAMPTZ,approved_by TEXT,rejected_at TIMESTAMPTZ,rejected_by TEXT,rejection_reason TEXT,cancelled_at TIMESTAMPTZ,cancelled_by TEXT,cancellation_reason TEXT,institution_id TEXT,unit_id TEXT,version INTEGER NOT NULL DEFAULT 1,created_at TIMESTAMPTZ NOT NULL,updated_at TIMESTAMPTZ NOT NULL,UNIQUE(tenant_id,requisition_number));
CREATE TABLE IF NOT EXISTS purchase_requisition_items(id TEXT PRIMARY KEY,tenant_id TEXT NOT NULL,requisition_id TEXT NOT NULL REFERENCES purchase_requisitions(id),product_id TEXT NOT NULL REFERENCES products(id),quantity NUMERIC NOT NULL,approved_quantity NUMERIC NOT NULL DEFAULT 0,estimated_unit_price NUMERIC NOT NULL DEFAULT 0,notes TEXT,created_at TIMESTAMPTZ NOT NULL);
CREATE TABLE IF NOT EXISTS requests_for_quotation(id TEXT PRIMARY KEY,tenant_id TEXT NOT NULL,quotation_number TEXT NOT NULL,requisition_id TEXT REFERENCES purchase_requisitions(id),response_deadline TIMESTAMPTZ,currency TEXT NOT NULL DEFAULT 'BRL',state TEXT NOT NULL DEFAULT 'open',selected_supplier_id TEXT REFERENCES suppliers(id),selection_reason TEXT,awarded_at TIMESTAMPTZ,awarded_by TEXT,institution_id TEXT,unit_id TEXT,version INTEGER NOT NULL DEFAULT 1,created_at TIMESTAMPTZ NOT NULL,updated_at TIMESTAMPTZ NOT NULL,UNIQUE(tenant_id,quotation_number));
CREATE TABLE IF NOT EXISTS quotation_items(id TEXT PRIMARY KEY,tenant_id TEXT NOT NULL,quotation_id TEXT NOT NULL REFERENCES requests_for_quotation(id),product_id TEXT NOT NULL REFERENCES products(id),quantity NUMERIC NOT NULL,specifications_json JSONB NOT NULL DEFAULT '{}'::jsonb,created_at TIMESTAMPTZ NOT NULL);
CREATE TABLE IF NOT EXISTS quotation_suppliers(id TEXT PRIMARY KEY,tenant_id TEXT NOT NULL,quotation_id TEXT NOT NULL REFERENCES requests_for_quotation(id),supplier_id TEXT NOT NULL REFERENCES suppliers(id),state TEXT NOT NULL DEFAULT 'invited',invited_at TIMESTAMPTZ NOT NULL,submitted_at TIMESTAMPTZ,delivery_days INTEGER,payment_terms_json JSONB NOT NULL DEFAULT '{}'::jsonb,notes TEXT,total_amount NUMERIC NOT NULL DEFAULT 0,created_at TIMESTAMPTZ NOT NULL,updated_at TIMESTAMPTZ NOT NULL,UNIQUE(tenant_id,quotation_id,supplier_id));
CREATE TABLE IF NOT EXISTS quotation_supplier_items(id TEXT PRIMARY KEY,tenant_id TEXT NOT NULL,quotation_supplier_id TEXT NOT NULL REFERENCES quotation_suppliers(id),quotation_item_id TEXT NOT NULL REFERENCES quotation_items(id),unit_price NUMERIC NOT NULL,quantity_available NUMERIC NOT NULL,brand TEXT,notes TEXT,created_at TIMESTAMPTZ NOT NULL,UNIQUE(tenant_id,quotation_supplier_id,quotation_item_id));
CREATE TABLE IF NOT EXISTS goods_receipts(id TEXT PRIMARY KEY,tenant_id TEXT NOT NULL,receipt_number TEXT NOT NULL,purchase_order_id TEXT NOT NULL REFERENCES purchase_orders(id),supplier_id TEXT NOT NULL REFERENCES suppliers(id),warehouse_id TEXT NOT NULL,state TEXT NOT NULL DEFAULT 'confirmed',received_at TIMESTAMPTZ NOT NULL,received_by TEXT NOT NULL,supplier_document_number TEXT,supplier_document_key TEXT,total_amount NUMERIC NOT NULL DEFAULT 0,notes TEXT,created_at TIMESTAMPTZ NOT NULL,updated_at TIMESTAMPTZ NOT NULL,UNIQUE(tenant_id,receipt_number));
CREATE TABLE IF NOT EXISTS goods_receipt_items(id TEXT PRIMARY KEY,tenant_id TEXT NOT NULL,goods_receipt_id TEXT NOT NULL REFERENCES goods_receipts(id),purchase_order_item_id TEXT NOT NULL REFERENCES purchase_order_items(id),product_id TEXT NOT NULL REFERENCES products(id),quantity NUMERIC NOT NULL,unit_cost NUMERIC NOT NULL,lot_id TEXT,stock_movement_id TEXT,expires_on DATE,created_at TIMESTAMPTZ NOT NULL);
CREATE TABLE IF NOT EXISTS inventory_lots(id TEXT PRIMARY KEY,tenant_id TEXT NOT NULL,product_id TEXT NOT NULL REFERENCES products(id),warehouse_id TEXT NOT NULL,lot_number TEXT NOT NULL,manufactured_on DATE,expires_on DATE,quantity NUMERIC NOT NULL DEFAULT 0,reserved_quantity NUMERIC NOT NULL DEFAULT 0,unit_cost NUMERIC NOT NULL DEFAULT 0,state TEXT NOT NULL DEFAULT 'active',created_at TIMESTAMPTZ NOT NULL,updated_at TIMESTAMPTZ NOT NULL,UNIQUE(tenant_id,product_id,warehouse_id,lot_number));
CREATE TABLE IF NOT EXISTS purchase_returns(id TEXT PRIMARY KEY,tenant_id TEXT NOT NULL,return_number TEXT NOT NULL,purchase_order_id TEXT NOT NULL REFERENCES purchase_orders(id),supplier_id TEXT NOT NULL REFERENCES suppliers(id),warehouse_id TEXT NOT NULL,reason TEXT NOT NULL,total_amount NUMERIC NOT NULL DEFAULT 0,state TEXT NOT NULL DEFAULT 'confirmed',returned_at TIMESTAMPTZ NOT NULL,returned_by TEXT NOT NULL,created_at TIMESTAMPTZ NOT NULL,updated_at TIMESTAMPTZ NOT NULL,UNIQUE(tenant_id,return_number));
CREATE TABLE IF NOT EXISTS purchase_return_items(id TEXT PRIMARY KEY,tenant_id TEXT NOT NULL,purchase_return_id TEXT NOT NULL REFERENCES purchase_returns(id),purchase_order_item_id TEXT NOT NULL REFERENCES purchase_order_items(id),product_id TEXT NOT NULL REFERENCES products(id),lot_id TEXT,quantity NUMERIC NOT NULL,unit_cost NUMERIC NOT NULL,stock_movement_id TEXT,created_at TIMESTAMPTZ NOT NULL);
CREATE TABLE IF NOT EXISTS inventory_reservations(id TEXT PRIMARY KEY,tenant_id TEXT NOT NULL,product_id TEXT NOT NULL REFERENCES products(id),warehouse_id TEXT NOT NULL,lot_id TEXT,source_type TEXT NOT NULL,source_id TEXT NOT NULL,quantity NUMERIC NOT NULL,consumed_quantity NUMERIC NOT NULL DEFAULT 0,state TEXT NOT NULL DEFAULT 'active',expires_at TIMESTAMPTZ,released_at TIMESTAMPTZ,consumed_at TIMESTAMPTZ,institution_id TEXT,unit_id TEXT,version INTEGER NOT NULL DEFAULT 1,created_at TIMESTAMPTZ NOT NULL,updated_at TIMESTAMPTZ NOT NULL,UNIQUE(tenant_id,source_type,source_id,product_id,warehouse_id,lot_id));
CREATE TABLE IF NOT EXISTS asset_locations(id TEXT PRIMARY KEY,tenant_id TEXT NOT NULL,code TEXT NOT NULL,name TEXT NOT NULL,parent_id TEXT REFERENCES asset_locations(id),state TEXT NOT NULL DEFAULT 'active',institution_id TEXT,unit_id TEXT,version INTEGER NOT NULL DEFAULT 1,created_at TIMESTAMPTZ NOT NULL,updated_at TIMESTAMPTZ NOT NULL,UNIQUE(tenant_id,code));
CREATE TABLE IF NOT EXISTS asset_movements(id TEXT PRIMARY KEY,tenant_id TEXT NOT NULL,asset_id TEXT NOT NULL REFERENCES assets(id),movement_type TEXT NOT NULL,from_location_id TEXT,to_location_id TEXT,from_responsible_person_id TEXT,to_responsible_person_id TEXT,reason TEXT NOT NULL,occurred_at TIMESTAMPTZ NOT NULL,occurred_by TEXT NOT NULL,created_at TIMESTAMPTZ NOT NULL);
CREATE TABLE IF NOT EXISTS asset_maintenances(id TEXT PRIMARY KEY,tenant_id TEXT NOT NULL,asset_id TEXT NOT NULL REFERENCES assets(id),maintenance_number TEXT NOT NULL,maintenance_type TEXT NOT NULL,scheduled_on DATE,supplier_id TEXT REFERENCES suppliers(id),estimated_cost NUMERIC NOT NULL DEFAULT 0,actual_cost NUMERIC,description TEXT NOT NULL,result_notes TEXT,state TEXT NOT NULL DEFAULT 'scheduled',started_at TIMESTAMPTZ,completed_at TIMESTAMPTZ,created_by TEXT NOT NULL,created_at TIMESTAMPTZ NOT NULL,updated_at TIMESTAMPTZ NOT NULL,UNIQUE(tenant_id,maintenance_number));
CREATE TABLE IF NOT EXISTS asset_loans(id TEXT PRIMARY KEY,tenant_id TEXT NOT NULL,asset_id TEXT NOT NULL REFERENCES assets(id),loan_number TEXT NOT NULL,borrower_person_id TEXT NOT NULL REFERENCES people(id),loaned_at TIMESTAMPTZ NOT NULL,expected_return_at TIMESTAMPTZ,returned_at TIMESTAMPTZ,condition_out TEXT,condition_in TEXT,state TEXT NOT NULL DEFAULT 'active',created_by TEXT NOT NULL,returned_by TEXT,created_at TIMESTAMPTZ NOT NULL,updated_at TIMESTAMPTZ NOT NULL,UNIQUE(tenant_id,loan_number));
CREATE TABLE IF NOT EXISTS asset_depreciations(id TEXT PRIMARY KEY,tenant_id TEXT NOT NULL,asset_id TEXT NOT NULL REFERENCES assets(id),competence TEXT NOT NULL,opening_book_value NUMERIC NOT NULL,depreciation_amount NUMERIC NOT NULL,accumulated_depreciation NUMERIC NOT NULL,closing_book_value NUMERIC NOT NULL,method TEXT NOT NULL DEFAULT 'linear',calculated_at TIMESTAMPTZ NOT NULL,calculated_by TEXT NOT NULL,created_at TIMESTAMPTZ NOT NULL,UNIQUE(tenant_id,asset_id,competence));
CREATE INDEX IF NOT EXISTS ix_service_prices_validity ON service_price_tables(tenant_id,service_id,variant_id,valid_from,valid_until,state);
CREATE INDEX IF NOT EXISTS ix_service_subscriptions_status ON service_subscriptions(tenant_id,state,next_competence_on);
CREATE INDEX IF NOT EXISTS ix_service_orders_status ON service_orders(tenant_id,state,created_at);
CREATE INDEX IF NOT EXISTS ix_requisitions_status ON purchase_requisitions(tenant_id,state,created_at);
CREATE INDEX IF NOT EXISTS ix_quotations_status ON requests_for_quotation(tenant_id,state,created_at);
CREATE INDEX IF NOT EXISTS ix_inventory_lots_expiry ON inventory_lots(tenant_id,warehouse_id,expires_on,state);
CREATE INDEX IF NOT EXISTS ix_inventory_reservations_product ON inventory_reservations(tenant_id,product_id,warehouse_id,state);
CREATE INDEX IF NOT EXISTS ix_asset_movements_asset ON asset_movements(tenant_id,asset_id,occurred_at);
"""


def upgrade() -> None:
    for table, columns in ALTER_COLUMNS.items():
        for definition in columns:
            op.execute(f'ALTER TABLE "{table}" ADD COLUMN IF NOT EXISTS {definition}')
    op.execute(DDL)
    for table in NEW_TABLES:
        op.execute(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY')
        op.execute(f'ALTER TABLE "{table}" FORCE ROW LEVEL SECURITY')
        op.execute(f'DROP POLICY IF EXISTS {table}_tenant_isolation ON "{table}"')
        op.execute(
            f"CREATE POLICY {table}_tenant_isolation ON \"{table}\" "
            "USING (tenant_id = current_setting('app.tenant_id', true)) "
            "WITH CHECK (tenant_id = current_setting('app.tenant_id', true))"
        )
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_service_orders_order_number ON service_orders(tenant_id,order_number) WHERE order_number IS NOT NULL")
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_assets_tag ON assets(tenant_id,tag) WHERE tag IS NOT NULL")
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_suppliers_code ON suppliers(tenant_id,code) WHERE code IS NOT NULL")


def downgrade() -> None:
    for table in reversed(NEW_TABLES):
        op.execute(f'DROP TABLE IF EXISTS "{table}" CASCADE')
    for table, columns in ALTER_COLUMNS.items():
        for definition in reversed(columns):
            column = definition.split()[0]
            op.execute(f'ALTER TABLE "{table}" DROP COLUMN IF EXISTS "{column}" CASCADE')
