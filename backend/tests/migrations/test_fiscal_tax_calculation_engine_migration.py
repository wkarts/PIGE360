from __future__ import annotations
import os, subprocess, sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[3]
CONFIG=ROOT/'backend'/'alembic_tenant'/'alembic.ini'
DATABASE_URL='postgresql+asyncpg://pige360_tenant:local-only@localhost:5432/tenant_template'

def _alembic(*args:str)->str:
    env=os.environ.copy();env['DATABASE_TENANT_URL']=DATABASE_URL
    result=subprocess.run([sys.executable,'-m','alembic','-c',str(CONFIG),*args,'--sql'],cwd=ROOT,env=env,text=True,capture_output=True,timeout=120,check=False)
    assert result.returncode==0,result.stdout+result.stderr
    return result.stdout+result.stderr

def test_0034_upgrade_creates_versioned_tax_engine_rls_and_audit_snapshot_tables():
    sql=_alembic('upgrade','0033_fiscal_catalogs_classifications:0034_fiscal_tax_calculation_engine')
    for table in ('fiscal_tax_rule_sets','fiscal_tax_rule_versions','fiscal_tax_calculations'):
        assert f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY' in sql
        assert f'CREATE POLICY {table}_tenant_isolation' in sql
    for token in ('ck_fiscal_tax_rule_set_rtc_mode','ck_fiscal_tax_rule_version_period','snapshot_sha256','ix_fiscal_tax_rule_sets_resolution','0034_fiscal_tax_calculation_engine'):
        assert token in sql

def test_0034_downgrade_removes_only_tax_engine_increment():
    sql=_alembic('downgrade','0034_fiscal_tax_calculation_engine:0033_fiscal_catalogs_classifications')
    for table in ('fiscal_tax_calculations','fiscal_tax_rule_versions','fiscal_tax_rule_sets'):
        assert f'DROP TABLE IF EXISTS "{table}"' in sql or f'DROP TABLE IF EXISTS {table}' in sql
    assert "version_num='0033_fiscal_catalogs_classifications'" in sql
    assert 'DROP TABLE IF EXISTS "fiscal_catalogs"' not in sql
