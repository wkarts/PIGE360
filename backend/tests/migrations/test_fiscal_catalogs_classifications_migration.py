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

def test_0033_upgrade_creates_versioned_catalogs_rls_and_classification_resolution():
    sql=_alembic('upgrade','0032_fiscal_context_versioning:0033_fiscal_catalogs_classifications')
    for table in ('fiscal_catalogs','fiscal_catalog_versions','fiscal_catalog_entries','fiscal_classification_rules'):
        assert f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY' in sql
        assert f'CREATE POLICY {table}_tenant_isolation' in sql
    for token in ('ck_fiscal_catalog_kind','ck_fiscal_catalog_version_period','ix_fiscal_classification_rules_resolution','CST_IBS_CBS','CCLASSTRIB','CBENEF'):
        assert token in sql
    assert '0033_fiscal_catalogs_classifications' in sql

def test_0033_downgrade_removes_only_increment():
    sql=_alembic('downgrade','0033_fiscal_catalogs_classifications:0032_fiscal_context_versioning')
    for table in ('fiscal_classification_rules','fiscal_catalog_entries','fiscal_catalog_versions','fiscal_catalogs'):
        assert f'DROP TABLE IF EXISTS "{table}"' in sql or f'DROP TABLE IF EXISTS {table}' in sql
    assert "version_num='0032_fiscal_context_versioning'" in sql
    assert 'DROP TABLE IF EXISTS "fiscal_contexts"' not in sql
