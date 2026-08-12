from __future__ import annotations
import json, os, re, subprocess, sys, time
from pathlib import Path
root=Path(__file__).resolve().parents[2]
files=sorted((root/'backend/tests').rglob('test_*.py'))
out=root/'docs/execution/evidence/backend-regression-fiscal-delivery-0041.json'
progress=root/'docs/execution/evidence/backend-regression-fiscal-delivery-0041.progress'
results=[]; total_passed=0; started=time.time()
env=os.environ.copy(); env['PYTHONPATH']=str(root/'backend')
for index,path in enumerate(files,1):
    rel=path.relative_to(root).as_posix()
    proc=subprocess.run([sys.executable,'-m','pytest','-q','-p','no:ddtrace',rel],cwd=root,env=env,text=True,capture_output=True,timeout=180)
    text=(proc.stdout or '')+'\n'+(proc.stderr or '')
    matches=re.findall(r'(\d+) passed',text); passed=int(matches[-1]) if matches else 0
    failed=proc.returncode!=0
    results.append({'file':rel,'exit_code':proc.returncode,'passed':passed,'output':text[-12000:]})
    total_passed+=passed
    progress.write_text(json.dumps({'completed_files':index,'total_files':len(files),'passed':total_passed,'failed_files':sum(1 for r in results if r['exit_code']!=0),'last_file':rel},ensure_ascii=False,indent=2))
    if failed: break
report={'total_files':len(files),'completed_files':len(results),'passed':total_passed,'failed_files':sum(1 for r in results if r['exit_code']!=0),'duration_seconds':round(time.time()-started,2),'results':results}
out.write_text(json.dumps(report,ensure_ascii=False,indent=2))
summary=root/'docs/execution/evidence/backend-final-regression-0041.log'
summary.write_text(f"{report['completed_files']}/{report['total_files']} files\n{report['passed']} passed\n{report['failed_files']} failed files\n{report['duration_seconds']} seconds\n")
print(json.dumps({k:report[k] for k in ['total_files','completed_files','passed','failed_files','duration_seconds']},ensure_ascii=False))
sys.exit(1 if report['failed_files'] else 0)
