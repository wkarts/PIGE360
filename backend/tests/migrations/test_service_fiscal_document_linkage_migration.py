from __future__ import annotations

import importlib.util
from pathlib import Path


PATH = Path(__file__).resolve().parents[2] / "alembic_tenant" / "versions" / "0042_service_fiscal_document_linkage.py"


def _module():
    spec = importlib.util.spec_from_file_location("m0042", PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_0042_links_service_fiscal_events_without_discarding_history(monkeypatch):
    module = _module()
    sql: list[str] = []
    monkeypatch.setattr(module.op, "execute", lambda value: sql.append(str(value)))

    module.upgrade()
    joined = "\n".join(sql)
    assert module.revision == "0042_service_fiscal_document_linkage"
    assert module.down_revision == "0041_fiscal_delivery_resilience_rendering"
    assert "ADD COLUMN IF NOT EXISTS fiscal_document_id" in joined
    assert "ADD COLUMN IF NOT EXISTS fiscal_assembly_id" in joined
    assert "CREATE INDEX IF NOT EXISTS ix_service_fiscal_event_document" in joined


def test_0042_downgrade_preserves_service_fiscal_history(monkeypatch):
    module = _module()
    sql: list[str] = []
    monkeypatch.setattr(module.op, "execute", lambda value: sql.append(str(value)))

    module.downgrade()
    joined = "\n".join(sql)
    assert "DROP INDEX IF EXISTS ix_service_fiscal_event_document" in joined
    assert "DROP COLUMN" not in joined
