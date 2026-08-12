from pathlib import Path
import importlib.util

PATH = Path(__file__).resolve().parents[2] / "alembic_tenant" / "versions" / "0040_fiscal_ibpt_transparency.py"


def _module():
    spec = importlib.util.spec_from_file_location("m0040", PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_0040_contract_and_rls(monkeypatch):
    module = _module(); sql = []
    monkeypatch.setattr(module.op, "execute", lambda value: sql.append(value))
    module.upgrade(); joined = "\n".join(sql)
    assert module.down_revision == "0039_fiscal_document_routing_assembly"
    assert module.TABLES == ("fiscal_ibpt_provider_profiles", "fiscal_document_tax_transparency")
    for table in module.TABLES:
        assert f"CREATE TABLE {table}" in joined
        assert f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY" in joined
        assert f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY" in joined
        assert f"CREATE POLICY {table}_tenant_isolation" in joined
    assert "real_taxes_json JSONB" in joined
    assert "approximate_ibpt_json JSONB" in joined
    assert "vtottrib NUMERIC(18,2)" in joined


def test_0040_downgrade(monkeypatch):
    module = _module(); sql = []
    monkeypatch.setattr(module.op, "execute", lambda value: sql.append(value))
    module.downgrade(); joined = "\n".join(sql)
    assert joined.index("DROP TABLE IF EXISTS fiscal_document_tax_transparency") < joined.index("DROP TABLE IF EXISTS fiscal_ibpt_provider_profiles")
