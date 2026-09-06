#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,re
from datetime import datetime,timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
SKIP_PARTS={'.git','node_modules','.venv','venv','__pycache__','.pytest_cache','generated-previews','runtime-data','runtime-secrets'}
SKIP_ROOT_PREFIXES={('release','output')}
TEXT_EXT={'.py','.ts','.js','.vue','.csv','.json','.log','.yaml','.yml','.toml','.md','.txt','.sh','.css','.scss','.html','.xml','.sql','.conf','.ini','.example'}
PATTERNS={
 'private_key':re.compile(r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----'),
 'github_token':re.compile(r'\bgh[pousr]_[A-Za-z0-9]{30,}\b'),
 'aws_access_key':re.compile(r'\bAKIA[0-9A-Z]{16}\b'),
 'jwt':re.compile(r'\beyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}\b'),
 'generic_password':re.compile(r'(?im)^\s*(?:password|secret|api[_-]?key|token)\s*[:=]\s*["\']?(?!\$\{|change|example|demo|test|local|not_configured|$)[A-Za-z0-9+/=_-]{20,}["\']?\s*(?:#.*)?$')
}

def skipped(relative:Path)->bool:
 if any(part in SKIP_PARTS for part in relative.parts):return True
 return any(relative.parts[:len(prefix)]==prefix for prefix in SKIP_ROOT_PREFIXES)

def scan(root:Path,*,strict:bool=False)->dict:
 findings=[];scanned=0
 for path in root.rglob('*'):
  if not path.is_file() or path.is_symlink():continue
  relative=path.relative_to(root)
  if skipped(relative):continue
  if path.suffix.lower() not in TEXT_EXT and path.name not in {'.env.example','Dockerfile'} and not path.name.startswith('Dockerfile.'):continue
  try:text=path.read_text(encoding='utf-8')
  except UnicodeDecodeError:continue
  scanned+=1
  for kind,pattern in PATTERNS.items():
   if kind == 'generic_password' and not strict and ('tests' in relative.parts or path.name.endswith('.example')): continue
   for match in pattern.finditer(text):
    line=text.count('\n',0,match.start())+1
    findings.append({'path':relative.as_posix(),'line':line,'kind':kind})
 return {'status':'passed' if not findings else 'failed','scanned_files':scanned,'findings':findings}

def main()->int:
 p=argparse.ArgumentParser();p.add_argument('--output');p.add_argument('--root');p.add_argument('--project-version');p.add_argument('--strict',action='store_true');a=p.parse_args()
 root=Path(a.root).expanduser().resolve() if a.root else ROOT
 if not root.is_dir():p.error(f'raiz inexistente: {root}')
 result=scan(root,strict=a.strict)
 version=a.project_version
 if version is None and (root/'VERSION').is_file():version=(root/'VERSION').read_text(encoding='utf-8').strip()
 result.update({'schema_version':2,'version':version,'generated_at':datetime.now(timezone.utc).isoformat(),'scan_root':'.','strict':a.strict})
 if a.output:Path(a.output).write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
 print(json.dumps(result,ensure_ascii=False,indent=2))
 return 0 if result['status']=='passed' else 1
if __name__=='__main__':raise SystemExit(main())
