from __future__ import annotations
import json, os, re, subprocess, sys, time
from pathlib import Path
root=Path(__file__).resolve().parents[2]
files=sorted((root/'backend/tests').rglob('test_*.py'))
start=int(sys.argv[1]); end=min(int(sys.argv[2]),len(files))
out=root/f'docs/execution/evidence/regression-final-0039-batch-{start:02d}-{end:02d}.json'
results=[]; total=0; started=time.time(); env=os.environ.copy(); env['PYTHONPATH']=str(root/'backend')
for index in range(start,end):
    path=files[index]; rel=path.relative_to(root).as_posix()
    proc=subprocess.run([sys.executable,'-m','pytest','-q','-p','no:ddtrace',rel],cwd=root,env=env,text=True,capture_output=True,timeout=180)
    text=(proc.stdout or '')+'\n'+(proc.stderr or '')
    matches=re.findall(r'(\d+) passed',text); passed=int(matches[-1]) if matches else 0
    results.append({'index':index,'file':rel,'exit_code':proc.returncode,'passed':passed,'output':text[-12000:]})
    total+=passed
    if proc.returncode!=0: break
report={'start':start,'end':end,'total_files':len(files),'completed_files':len(results),'passed':total,'failed_files':sum(r['exit_code']!=0 for r in results),'duration_seconds':round(time.time()-started,2),'results':results}
out.write_text(json.dumps(report,ensure_ascii=False,indent=2))
print(json.dumps({k:report[k] for k in ['start','end','completed_files','passed','failed_files','duration_seconds']},ensure_ascii=False))
sys.exit(1 if report['failed_files'] else 0)
