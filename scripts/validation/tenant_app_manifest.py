#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,re,sys
from pathlib import Path
import yaml
RUNNERS={'android':'ubuntu-24.04','ios':'macos-15','windows':'windows-2025','linux':'ubuntu-24.04','macos':'macos-15','pwa':'ubuntu-24.04'}
def main()->int:
 p=argparse.ArgumentParser();p.add_argument('manifest');p.add_argument('--github-output',action='store_true');a=p.parse_args()
 path=Path(a.manifest);data=yaml.safe_load(path.read_text(encoding='utf-8'))
 errors=[]
 for key in ['tenant_id','tenant_code','brand_version','manifest_version','release_channel','apps']:
  if key not in data:errors.append(f'campo ausente: {key}')
 matrix=[];ids=set()
 for app,cfg in (data.get('apps') or {}).items():
  if not cfg.get('enabled'):continue
  ident=str(cfg.get('identifier',''))
  if not re.fullmatch(r'[A-Za-z][A-Za-z0-9]*(\.[A-Za-z][A-Za-z0-9_-]*){2,}',ident):errors.append(f'identificador inválido: {app}')
  if ident in ids:errors.append(f'identificador duplicado: {ident}')
  ids.add(ident)
  for platform in cfg.get('platforms',[]):
   if platform not in RUNNERS:errors.append(f'plataforma desconhecida: {platform}');continue
   matrix.append({'app':app,'platform':platform,'runner':RUNNERS[platform]})
 if errors:print(json.dumps({'status':'failed','errors':errors},ensure_ascii=False));return 1
 output={'include':matrix}
 if a.github_output:
  target=Path(__import__('os').environ.get('GITHUB_OUTPUT','/dev/stdout'))
  with target.open('a',encoding='utf-8') as f:f.write('matrix='+json.dumps(output,separators=(',',':'))+'\n')
 else:print(json.dumps({'status':'passed','matrix':output},ensure_ascii=False,indent=2))
 return 0
if __name__=='__main__':raise SystemExit(main())
