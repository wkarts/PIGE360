from __future__ import annotations
import os, subprocess, sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[3]
CONFIG=ROOT/'backend'/'alembic_tenant'/'alembic.ini'
DB='postgresql+asyncpg://pige360_tenant:local-only@localhost:5432/tenant_template'

def _a(*args):
    env=os.environ.copy(); env['DATABASE_TENANT_URL']=DB
    result=subprocess.run([sys.executable,'-m','alembic','-c',str(CONFIG),*args,'--sql'],cwd=ROOT,env=env,text=True,capture_output=True,timeout=120)
    assert result.returncode==0,result.stdout+result.stderr
    return result.stdout+result.stderr

def test_0037_upgrade_creates_governance_tables_rls_and_new_kinds():
    sql=_a('upgrade','0036_ibpt_operational_resilience:0037_fiscal_catalog_governance_imports')
    for table in ('fiscal_catalog_source_profiles','fiscal_catalog_import_runs','fiscal_catalog_quarantine'):
        assert table in sql
        assert f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY' in sql
        assert f'CREATE POLICY {table}_tenant_isolation' in sql
    assert 'CREDITO_PRESUMIDO' in sql
    assert 'RTC_TABLE' in sql
    assert 'ix_fiscal_catalog_import_runs_catalog' in sql

def test_0037_downgrade_removes_only_governance_tables():
    sql=_a('downgrade','0037_fiscal_catalog_governance_imports:0036_ibpt_operational_resilience')
    for table in ('fiscal_catalog_quarantine','fiscal_catalog_import_runs','fiscal_catalog_source_profiles'):
        assert f'DROP TABLE IF EXISTS "{table}"' in sql
    assert 'DROP TABLE IF EXISTS "fiscal_catalogs"' not in sql
