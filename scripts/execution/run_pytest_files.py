#!/usr/bin/env python3
from __future__ import annotations
import json, os, re, subprocess, sys, time
from pathlib import Path

root=Path(__file__).resolve().parents[2]
files=[Path(x) for x in sys.argv[1:]]
if not files:
    raise SystemExit('Informe arquivos de teste')
env=os.environ.copy(); env['PYTHONPATH']=str(root/'backend'); env['PYTEST_DISABLE_PLUGIN_AUTOLOAD']='1'
results=[]; total_passed=0; started=time.time()
for rel in files:
    path=rel if rel.is_absolute() else root/rel
    t=time.time()
    try:
        cp=subprocess.run([sys.executable,'-m','pytest','-q',str(path)],cwd=root,env=env,text=True,capture_output=True,timeout=150)
        text=(cp.stdout or '')+(cp.stderr or '')
        m=re.search(r'(\d+) passed',text)
        passed=int(m.group(1)) if m else 0
        total_passed += passed
        results.append({'file':str(path.relative_to(root)),'exit_code':cp.returncode,'passed':passed,'seconds':round(time.time()-t,2),'tail':'\n'.join(text.splitlines()[-8:])})
        print(f"{path.relative_to(root)} exit={cp.returncode} passed={passed} seconds={time.time()-t:.2f}",flush=True)
        if cp.returncode!=0:
            print(text,flush=True); break
    except subprocess.TimeoutExpired as exc:
        results.append({'file':str(path.relative_to(root)),'exit_code':124,'passed':0,'seconds':round(time.time()-t,2),'tail':'TIMEOUT'})
        print(f"{path.relative_to(root)} TIMEOUT",flush=True); break
summary={'files':len(results),'passed':total_passed,'failed_files':sum(1 for r in results if r['exit_code']!=0),'seconds':round(time.time()-started,2),'results':results}
print('SUMMARY '+json.dumps({k:summary[k] for k in ('files','passed','failed_files','seconds')},ensure_ascii=False),flush=True)
out=os.environ.get('PIGE360_PYTEST_GROUP_REPORT')
if out: (root/out).write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
raise SystemExit(0 if summary['failed_files']==0 and len(results)==len(files) else 1)
