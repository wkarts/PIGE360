#!/usr/bin/env python3
from __future__ import annotations
import json, os, re, subprocess, sys, time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
root=Path(__file__).resolve().parents[2]
files=[Path(x) for x in sys.argv[1:]]
env=os.environ.copy(); env['PYTHONPATH']=str(root/'backend'); env['PYTEST_DISABLE_PLUGIN_AUTOLOAD']='1'
def run(rel:Path):
    path=rel if rel.is_absolute() else root/rel; t=time.time()
    try:
        cp=subprocess.run([sys.executable,'-m','pytest','-q',str(path)],cwd=root,env=env,text=True,capture_output=True,timeout=150)
        text=(cp.stdout or '')+(cp.stderr or ''); m=re.search(r'(\d+) passed',text)
        return {'file':str(path.relative_to(root)),'exit_code':cp.returncode,'passed':int(m.group(1)) if m else 0,'seconds':round(time.time()-t,2),'tail':'\n'.join(text.splitlines()[-8:])}
    except subprocess.TimeoutExpired:
        return {'file':str(path.relative_to(root)),'exit_code':124,'passed':0,'seconds':round(time.time()-t,2),'tail':'TIMEOUT'}
start=time.time(); results=[]
with ThreadPoolExecutor(max_workers=min(6,len(files))) as ex:
    futs={ex.submit(run,f):f for f in files}
    for fut in as_completed(futs):
        r=fut.result(); results.append(r); print(f"{r['file']} exit={r['exit_code']} passed={r['passed']} seconds={r['seconds']}",flush=True)
results.sort(key=lambda r:r['file'])
summary={'files':len(results),'passed':sum(r['passed'] for r in results),'failed_files':sum(r['exit_code']!=0 for r in results),'seconds':round(time.time()-start,2),'results':results}
print('SUMMARY '+json.dumps({k:summary[k] for k in ('files','passed','failed_files','seconds')},ensure_ascii=False))
out=os.environ.get('PIGE360_PYTEST_GROUP_REPORT')
if out:(root/out).write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
raise SystemExit(0 if summary['failed_files']==0 else 1)
