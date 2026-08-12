"""Resiliência operacional do IBPT: quarentena, rollback e distribuição offline."""
from __future__ import annotations

from alembic import op

revision = "0036_ibpt_operational_resilience"
down_revision = "0035_fiscal_strategies_rtc_schedule"
branch_labels = None
depends_on = None

TABLES = ("ibpt_quarantine_items",)

DDL = r"""
CREATE TABLE IF NOT EXISTS ibpt_quarantine_items (
  id TEXT PRIMARY KEY,
  tenant_id TEXT NOT NULL,
  sync_run_id TEXT NOT NULL,
  uf TEXT NOT NULL,
  source_url TEXT,
  sha256 TEXT NOT NULL,
  storage_key TEXT NOT NULL,
  bytes_count INTEGER NOT NULL,
  reason_code TEXT NOT NULL,
  reason_message TEXT NOT NULL,
  state TEXT NOT NULL DEFAULT 'open',
  created_at TIMESTAMPTZ NOT NULL,
  resolved_at TIMESTAMPTZ,
  resolved_by TEXT,
  CONSTRAINT ck_ibpt_quarantine_uf CHECK (uf ~ '^[A-Z]{2}$'),
  CONSTRAINT ck_ibpt_quarantine_sha CHECK (sha256 ~ '^[a-fA-F0-9]{64}$'),
  CONSTRAINT ck_ibpt_quarantine_state CHECK (state IN ('open','resolved','discarded')),
  UNIQUE(tenant_id,sync_run_id,sha256)
);
CREATE INDEX IF NOT EXISTS ix_ibpt_quarantine_open ON ibpt_quarantine_items(tenant_id,state,uf,created_at);
"""


def upgrade() -> None:
    op.execute(DDL)
    for table in TABLES:
        op.execute(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY')
        op.execute(f'ALTER TABLE "{table}" FORCE ROW LEVEL SECURITY')
        op.execute(f'DROP POLICY IF EXISTS {table}_tenant_isolation ON "{table}"')
        op.execute(
            f'CREATE POLICY {table}_tenant_isolation ON "{table}" '
            "USING (tenant_id = current_setting('app.tenant_id', true)) "
            "WITH CHECK (tenant_id = current_setting('app.tenant_id', true))"
        )


def downgrade() -> None:
    op.execute('DROP TABLE IF EXISTS "ibpt_quarantine_items" CASCADE')
