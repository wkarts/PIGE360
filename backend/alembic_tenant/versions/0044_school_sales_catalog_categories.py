"""Add school-specific product categories to the sales catalog.

Revision ID: 0044_school_sales_catalog_categories
Revises: 0043_service_payment_receipts
"""
from alembic import op


revision = "0044_school_sales_catalog_categories"
down_revision = "0043_service_payment_receipts"
branch_labels = None
depends_on = None


CATEGORIES = (
    "general",
    "school_uniform",
    "textbook",
    "handout",
    "learning_module",
    "educational_material",
    "school_kit",
    "event_ticket",
    "event",
)


def upgrade() -> None:
    op.execute(
        "ALTER TABLE products ADD COLUMN IF NOT EXISTS "
        "school_catalog_category TEXT NOT NULL DEFAULT 'general'"
    )
    op.execute(
        "UPDATE products SET school_catalog_category = CASE product_type "
        "WHEN 'uniform' THEN 'school_uniform' "
        "WHEN 'book' THEN 'textbook' "
        "WHEN 'material' THEN 'educational_material' "
        "WHEN 'kit' THEN 'school_kit' "
        "ELSE school_catalog_category END "
        "WHERE school_catalog_category = 'general'"
    )
    allowed = ", ".join(repr(category) for category in CATEGORIES)
    op.execute(
        "ALTER TABLE products ADD CONSTRAINT ck_products_school_catalog_category "
        f"CHECK (school_catalog_category IN ({allowed})) NOT VALID"
    )
    op.execute(
        "ALTER TABLE products VALIDATE CONSTRAINT ck_products_school_catalog_category"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_products_school_catalog_category "
        "ON products(tenant_id, school_catalog_category, state)"
    )


def downgrade() -> None:
    # Categorias são metadados comerciais já usados por vendas; o rollback preserva dados.
    op.execute("DROP INDEX IF EXISTS ix_products_school_catalog_category")

