from __future__ import annotations

import importlib.util
from pathlib import Path


PATH = Path(__file__).resolve().parents[2] / "alembic_tenant" / "versions" / "0043_service_payment_receipts.py"


def _module():
    spec = importlib.util.spec_from_file_location("m0043", PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_0043_creates_isolated_receipts_with_active_payment_uniqueness(monkeypatch):
    module = _module()
    sql: list[str] = []
    monkeypatch.setattr(module.op, "execute", lambda value: sql.append(str(value)))

    module.upgrade()
    joined = "\n".join(sql)
    assert module.revision == "0043_service_payment_receipts"
    assert module.down_revision == "0042_service_fiscal_document_linkage"
    assert "CREATE TABLE IF NOT EXISTS service_receipts" in joined
    assert "document_sha256" in joined
    assert "ux_service_receipts_active_payment" in joined
    assert "ENABLE ROW LEVEL SECURITY" in joined
    assert "service_receipts_tenant_isolation" in joined


def test_0043_downgrade_preserves_financial_document_history(monkeypatch):
    module = _module()
    sql: list[str] = []
    monkeypatch.setattr(module.op, "execute", lambda value: sql.append(str(value)))

    module.downgrade()
    joined = "\n".join(sql)
    assert "DROP INDEX IF EXISTS ux_service_receipts_active_payment" in joined
    assert "DROP TABLE" not in joined

