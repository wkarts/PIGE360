#!/usr/bin/env python3
from __future__ import annotations
import json,re
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];errors=[];records=[]
for p in sorted((ROOT/'infra/docker').rglob('Dockerfile*')):
 text=p.read_text(encoding='utf-8');name=p.relative_to(ROOT).as_posix();issues=[]
 if re.search(r'(?im)^FROM\s+\S+:latest\b',text):issues.append('imagem latest')
 if 'LABEL org.opencontainers.image.' not in text:issues.append('labels OCI ausentes')
 users=re.findall(r'(?im)^USER\s+([^\s]+)',text)
 if not users or users[-1] in {'root','0','0:0'}:issues.append('estágio final sem usuário não root')
 if re.search(r'(?i)(password|secret|token)\s*=\s*[A-Za-z0-9+/]{20,}',text):issues.append('possível segredo embutido')
 if p.name=='Dockerfile.web':
  if 'ARG NPM_INSTALL_MODE=ci' not in text:issues.append('build web não usa npm ci por padrão')
  if 'test -s package-lock.json && npm ci' not in text:issues.append('build web não exige lockfile no modo reproduzível')
 records.append({'path':name,'final_user':users[-1] if users else None,'issues':issues});errors.extend(f'{name}: {x}' for x in issues)
print(json.dumps({'status':'passed' if not errors else 'failed','dockerfiles':records,'errors':errors},ensure_ascii=False,indent=2))
raise SystemExit(0 if not errors else 1)
