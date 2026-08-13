"""Link service fiscal intents to the generated fiscal document lifecycle.

Revision ID: 0042_service_fiscal_document_linkage
Revises: 0041_fiscal_delivery_resilience_rendering
"""
from alembic import op


revision = "0042_service_fiscal_document_linkage"
down_revision = "0041_fiscal_delivery_resilience_rendering"
branch_labels = None
depends_on = None

DDL = """
ALTER TABLE service_fiscal_events ADD COLUMN IF NOT EXISTS fiscal_document_id TEXT REFERENCES fiscal_documents(id);
ALTER TABLE service_fiscal_events ADD COLUMN IF NOT EXISTS fiscal_assembly_id TEXT REFERENCES fiscal_document_assemblies(id);
CREATE INDEX IF NOT EXISTS ix_service_fiscal_event_document
  ON service_fiscal_events(tenant_id,fiscal_document_id,state,updated_at);
"""


def upgrade() -> None:
    op.execute(DDL)


def downgrade() -> None:
    # Os vínculos formam trilha fiscal/auditável e são preservados no rollback lógico.
    op.execute("DROP INDEX IF EXISTS ix_service_fiscal_event_document")
