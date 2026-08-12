from __future__ import annotations
from pathlib import Path
import importlib.util

PATH=Path(__file__).resolve().parents[2]/"alembic_tenant"/"versions"/"0038_fiscal_document_lifecycle.py"

def _module():
    spec=importlib.util.spec_from_file_location("m0038",PATH);module=importlib.util.module_from_spec(spec);assert spec and spec.loader;spec.loader.exec_module(module);return module

def test_migration_0038_declares_lifecycle_tables_rls_and_monotonic_columns():
    module=_module();ddl=module.DDL
    assert module.revision=="0038_fiscal_document_lifecycle" and module.down_revision=="0037_fiscal_catalog_governance_imports"
    for table in ("fiscal_certificate_metadata","fiscal_provider_configurations","fiscal_document_attempts","fiscal_document_artifacts","fiscal_inutilization_requests","fiscal_provider_event_requests"):
        assert f"CREATE TABLE IF NOT EXISTS {table}" in ddl
        assert table in module.TABLES
    for column in ("replacement_of_document_id","substituted_by_document_id","contingency_mode","authorized_at","cancelled_at"):
        assert f"ADD COLUMN IF NOT EXISTS {column}" in ddl

def test_migration_0038_upgrade_forces_rls_and_downgrade_preserves_document_history(monkeypatch):
    module=_module();executed=[];monkeypatch.setattr(module.op,"execute",lambda sql:executed.append(str(sql)))
    module.upgrade();text="\n".join(executed)
    assert "FORCE ROW LEVEL SECURITY" in text and "current_setting('app.tenant_id', true)" in text
    executed.clear();module.downgrade();down="\n".join(executed)
    assert "DROP TABLE IF EXISTS" in down and "DROP COLUMN" not in down
