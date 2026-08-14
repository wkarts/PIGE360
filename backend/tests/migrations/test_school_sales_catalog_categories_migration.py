from __future__ import annotations

import importlib.util
from pathlib import Path


PATH = (
    Path(__file__).resolve().parents[2]
    / "alembic_tenant"
    / "versions"
    / "0044_school_sales_catalog_categories.py"
)


def _module():
    spec = importlib.util.spec_from_file_location("m0044", PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_0044_adds_compatible_school_sales_categories(monkeypatch):
    module = _module()
    sql: list[str] = []
    monkeypatch.setattr(module.op, "execute", lambda value: sql.append(str(value)))

    module.upgrade()

    joined = "\n".join(sql)
    assert module.revision == "0044_school_sales_catalog_categories"
    assert module.down_revision == "0043_service_payment_receipts"
    assert "ADD COLUMN IF NOT EXISTS school_catalog_category" in joined
    assert "school_uniform" in joined
    assert "event_ticket" in joined
    assert "ck_products_school_catalog_category" in joined
    assert "ix_products_school_catalog_category" in joined


def test_0044_downgrade_preserves_catalog_classification(monkeypatch):
    module = _module()
    sql: list[str] = []
    monkeypatch.setattr(module.op, "execute", lambda value: sql.append(str(value)))

    module.downgrade()

    joined = "\n".join(sql)
    assert "DROP INDEX IF EXISTS ix_products_school_catalog_category" in joined
    assert "DROP COLUMN" not in joined

