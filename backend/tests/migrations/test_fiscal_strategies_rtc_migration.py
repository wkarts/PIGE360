from __future__ import annotations
import os,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]; CONFIG=ROOT/'backend'/'alembic_tenant'/'alembic.ini'; DB='postgresql+asyncpg://pige360_tenant:local-only@localhost:5432/tenant_template'
def _a(*args):
 e=os.environ.copy();e['DATABASE_TENANT_URL']=DB;r=subprocess.run([sys.executable,'-m','alembic','-c',str(CONFIG),*args,'--sql'],cwd=ROOT,env=e,text=True,capture_output=True,timeout=120);assert r.returncode==0,r.stdout+r.stderr;return r.stdout+r.stderr
def test_0035_upgrade():
 s=_a('upgrade','0034_fiscal_tax_calculation_engine:0035_fiscal_strategies_rtc_schedule')
 for t in ('fiscal_legal_source_artifacts','fiscal_strategy_rules','fiscal_rtc_schedules'):
  assert f'ALTER TABLE "{t}" ENABLE ROW LEVEL SECURITY' in s and f'CREATE POLICY {t}_tenant_isolation' in s
def test_0035_downgrade():
 s=_a('downgrade','0035_fiscal_strategies_rtc_schedule:0034_fiscal_tax_calculation_engine'); assert 'DROP TABLE IF EXISTS "fiscal_rtc_schedules"' in s and "version_num='0034_fiscal_tax_calculation_engine'" in s
