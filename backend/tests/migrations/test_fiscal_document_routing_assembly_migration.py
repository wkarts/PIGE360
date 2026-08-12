from pathlib import Path
import importlib.util

PATH=Path(__file__).resolve().parents[2]/'alembic_tenant'/'versions'/'0039_fiscal_document_routing_assembly.py'

def _module():
    spec=importlib.util.spec_from_file_location('m0039',PATH);mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod);return mod

def test_0039_contract_and_rls(monkeypatch):
    m=_module();sql=[];monkeypatch.setattr(m.op,'execute',lambda value:sql.append(value));m.upgrade();joined='\n'.join(sql)
    for table in m.TABLES:
        assert f'CREATE TABLE {table}' in joined
        assert f'ALTER TABLE {table} ENABLE ROW LEVEL SECURITY' in joined
        assert f'ALTER TABLE {table} FORCE ROW LEVEL SECURITY' in joined
        assert f'CREATE POLICY {table}_tenant_isolation' in joined
    assert m.down_revision=='0038_fiscal_document_lifecycle'

def test_0039_downgrade(monkeypatch):
    m=_module();sql=[];monkeypatch.setattr(m.op,'execute',lambda value:sql.append(value));m.downgrade();joined='\n'.join(sql)
    for table in m.TABLES: assert f'DROP TABLE IF EXISTS {table} CASCADE' in joined
