from __future__ import annotations

import importlib.util
from pathlib import Path

PATH = Path(__file__).resolve().parents[2] / "alembic_tenant" / "versions" / "0041_fiscal_delivery_resilience_rendering.py"


def _module():
    spec = importlib.util.spec_from_file_location("m0041", PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_0041_contract_tables_columns_and_rls(monkeypatch):
    module = _module(); sql: list[str] = []
    monkeypatch.setattr(module.op, "execute", lambda value: sql.append(str(value)))
    module.upgrade(); joined = "\n".join(sql)
    assert module.revision == "0041_fiscal_delivery_resilience_rendering"
    assert module.down_revision == "0040_fiscal_ibpt_transparency"
    for table in module.TABLES:
        assert f"CREATE TABLE IF NOT EXISTS {table}" in joined
        assert f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY" in joined
        assert f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY" in joined
        assert f"CREATE POLICY {table}_tenant_isolation" in joined
    for column in ("delivery_policy_id", "retry_count", "next_retry_at"):
        assert f"ADD COLUMN IF NOT EXISTS {column}" in joined


def test_0041_downgrade_preserves_fiscal_document_history(monkeypatch):
    module = _module(); sql: list[str] = []
    monkeypatch.setattr(module.op, "execute", lambda value: sql.append(str(value)))
    module.downgrade(); joined = "\n".join(sql)
    assert "DROP TABLE IF EXISTS fiscal_document_rejections CASCADE" in joined
    assert "DROP TABLE IF EXISTS fiscal_document_delivery_policies CASCADE" in joined
    assert "DROP COLUMN" not in joined
