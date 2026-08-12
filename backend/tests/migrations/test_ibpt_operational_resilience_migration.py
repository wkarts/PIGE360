from __future__ import annotations
import os,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]; CONFIG=ROOT/'backend'/'alembic_tenant'/'alembic.ini'; DB='postgresql+asyncpg://pige360_tenant:local-only@localhost:5432/tenant_template'
def _a(*args):
 e=os.environ.copy();e['DATABASE_TENANT_URL']=DB;r=subprocess.run([sys.executable,'-m','alembic','-c',str(CONFIG),*args,'--sql'],cwd=ROOT,env=e,text=True,capture_output=True,timeout=120);assert r.returncode==0,r.stdout+r.stderr;return r.stdout+r.stderr
def test_0036_upgrade():
 s=_a('upgrade','0035_fiscal_strategies_rtc_schedule:0036_ibpt_operational_resilience'); assert 'ibpt_quarantine_items' in s and 'ENABLE ROW LEVEL SECURITY' in s
def test_0036_downgrade():
 s=_a('downgrade','0036_ibpt_operational_resilience:0035_fiscal_strategies_rtc_schedule'); assert 'DROP TABLE IF EXISTS "ibpt_quarantine_items"' in s
