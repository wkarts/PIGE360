#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,platform,shutil,subprocess,sys
from datetime import datetime,timezone
from pathlib import Path
TOOLS={'python':['python','--version'],'node':['node','--version'],'npm':['npm','--version'],'tsc':['tsc','--version'],'chromium':['chromium','--version'],'docker':['docker','--version'],'podman':['podman','--version'],'cargo':['cargo','--version'],'rustc':['rustc','--version'],'gradle':['gradle','--version'],'java':['java','-version'],'xcodebuild':['xcodebuild','-version'],'alembic':['alembic','--version'],'pytest':['pytest','--version']}
def probe(cmd):
 exe=shutil.which(cmd[0])
 if not exe:return {'available':False,'path':None,'version':None}
 try:r=subprocess.run(cmd,capture_output=True,text=True,timeout=15);version=(r.stdout or r.stderr).strip().splitlines()[0]
 except Exception as e:version=f'erro: {e}'
 return {'available':True,'path':exe,'version':version}
def main():
 p=argparse.ArgumentParser();p.add_argument('--output',default='release/toolchain-inventory.json');a=p.parse_args()
 data={'schema_version':1,'generated_at':datetime.now(timezone.utc).isoformat(),'platform':platform.platform(),'python_runtime':sys.version,'tools':{k:probe(v) for k,v in TOOLS.items()},'network_used':False}
 out=Path(a.output);out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(data,ensure_ascii=False))
if __name__=='__main__':main()
