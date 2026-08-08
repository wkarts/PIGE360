#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,re
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
SKIP={'.git','node_modules','.venv','venv','__pycache__','.pytest_cache','generated-previews','release','runtime-data','runtime-secrets'}
TEXT_EXT={'.py','.ts','.js','.vue','.json','.yaml','.yml','.toml','.md','.txt','.sh','.css','.scss','.html','.xml','.sql','.conf','.ini','.example'}
PATTERNS={
 'private_key':re.compile(r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----'),
 'github_token':re.compile(r'\bgh[pousr]_[A-Za-z0-9]{30,}\b'),
 'aws_access_key':re.compile(r'\bAKIA[0-9A-Z]{16}\b'),
 'jwt':re.compile(r'\beyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}\b'),
 'generic_password':re.compile(r'(?im)^\s*(?:password|secret|api[_-]?key|token)\s*[:=]\s*["\']?(?!\$\{|change|example|demo|test|local|not_configured|$)[A-Za-z0-9+/=_-]{20,}')
}
def main()->int:
 p=argparse.ArgumentParser();p.add_argument('--output');a=p.parse_args();findings=[];scanned=0
 for path in ROOT.rglob('*'):
  if not path.is_file() or any(part in SKIP for part in path.parts):continue
  if path.suffix.lower() not in TEXT_EXT and path.name not in {'.env.example','Dockerfile'} and not path.name.startswith('Dockerfile.'):continue
  try:text=path.read_text(encoding='utf-8')
  except UnicodeDecodeError:continue
  scanned+=1
  for kind,pattern in PATTERNS.items():
   if kind == 'generic_password' and ('tests' in path.parts or path.name.endswith('.example')): continue
   for match in pattern.finditer(text):
    line=text.count('\n',0,match.start())+1
    findings.append({'path':path.relative_to(ROOT).as_posix(),'line':line,'kind':kind})
 result={'status':'passed' if not findings else 'failed','scanned_files':scanned,'findings':findings}
 if a.output:Path(a.output).write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
 print(json.dumps(result,ensure_ascii=False,indent=2))
 return 0 if not findings else 1
if __name__=='__main__':raise SystemExit(main())
