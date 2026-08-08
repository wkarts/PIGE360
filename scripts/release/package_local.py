#!/usr/bin/env python3
from __future__ import annotations
import argparse,hashlib,json,os,shutil,stat,tempfile,zipfile
from datetime import datetime,timezone
from pathlib import Path
from typing import Callable

ROOT=Path(__file__).resolve().parents[2]
VERSION=(ROOT/'VERSION').read_text().strip()
DELIVERY=Path('/mnt/data/PIGE360_V8_LOCAL_DELIVERY')
FIXED=(2026,8,7,0,0,0)
EXCLUDED_PARTS={'.git','node_modules','__pycache__','.pytest_cache','.mypy_cache','.ruff_cache','.venv','venv','runtime-data','release-output'}
EXCLUDED_SUFFIX={'.pyc','.pyo','.ttf','.otf','.woff','.woff2','.eot'}

def sha(path:Path)->str:
 h=hashlib.sha256()
 with path.open('rb') as f:
  for chunk in iter(lambda:f.read(1024*1024),b''):h.update(chunk)
 return h.hexdigest()
def allowed(path:Path)->bool:
 rel=path.relative_to(ROOT)
 if any(p in EXCLUDED_PARTS for p in rel.parts):return False
 if rel.parts[:2]==('release','output'):return False
 if rel.parts[:2]==('release','.openapi-runtime'):return False
 if path.suffix.lower() in EXCLUDED_SUFFIX:return False
 if rel.parts and rel.parts[0]=='runtime-secrets' and path.suffix=='.txt':return False
 return path.is_file()
def source_entries():return [(p.relative_to(ROOT).as_posix(),p) for p in sorted(ROOT.rglob('*')) if allowed(p)]
def select_entries(prefixes:list[str],extras:list[str]=[]):
 result=[]
 for arc,p in source_entries():
  if any(arc==x or arc.startswith(x.rstrip('/')+'/') for x in prefixes+extras):result.append((arc,p))
 return result
def make_zip(path:Path,entries:list[tuple[str,Path]],external:list[tuple[str,Path]]=[])->dict:
 path.parent.mkdir(parents=True,exist_ok=True);seen=set()
 with zipfile.ZipFile(path,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=9,strict_timestamps=True) as z:
  for arc,src in sorted(entries+external,key=lambda x:x[0]):
   arc=arc.replace('\\','/').lstrip('/')
   if not arc or '..' in Path(arc).parts or arc in seen:raise RuntimeError(f'caminho de archive inválido/duplicado: {arc}')
   seen.add(arc);data=src.read_bytes();info=zipfile.ZipInfo(arc,FIXED);mode=src.stat().st_mode
   info.external_attr=((mode & 0o777) or 0o644)<<16;info.compress_type=zipfile.ZIP_DEFLATED;info.create_system=3;z.writestr(info,data,compress_type=zipfile.ZIP_DEFLATED,compresslevel=9)
 with zipfile.ZipFile(path) as z:
  if z.testzip() is not None:raise RuntimeError(f'ZIP corrompido: {path}')
 return {'name':path.name,'path':str(path),'sha256':sha(path),'bytes':path.stat().st_size,'files':len(seen)}
def tree_manifest(entries):
 files=[{'path':arc,'sha256':sha(p),'bytes':p.stat().st_size} for arc,p in entries]
 digest=hashlib.sha256(''.join(f"{x['sha256']}  {x['path']}\n" for x in files).encode()).hexdigest()
 data={'schema_version':1,'version':VERSION,'files_count':len(files),'tree_sha256':digest,'files':files}
 (ROOT/'release/source-tree-manifest.json').write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
 (ROOT/'release/final-tree.txt').write_text('\n'.join(x['path'] for x in files)+'\n',encoding='utf-8')
 return data
def validate_archives(packages:list[dict])->dict:
 errors=[];details=[]
 for pkg in packages:
  path=Path(pkg['path'])
  with zipfile.ZipFile(path) as z:
   names=z.namelist();bad=[n for n in names if n.startswith('/') or '..' in Path(n).parts];forbidden=[n for n in names if any(part in EXCLUDED_PARTS for part in Path(n).parts) or Path(n).suffix.lower() in EXCLUDED_SUFFIX or (n.startswith('runtime-secrets/') and n.endswith('.txt'))]
   if bad:errors.append({'archive':path.name,'path_traversal':bad[:10]})
   if forbidden:errors.append({'archive':path.name,'forbidden':forbidden[:20]})
   details.append({'archive':path.name,'files':len(names),'testzip':z.testzip(),'path_traversal':len(bad),'forbidden':len(forbidden)})
 return {'status':'passed' if not errors else 'failed','archives':details,'errors':errors}
def main():
 parser=argparse.ArgumentParser();parser.add_argument('--output-dir',default=str(DELIVERY));a=parser.parse_args();delivery=Path(a.output_dir)
 if delivery.exists():shutil.rmtree(delivery)
 delivery.mkdir(parents=True)
 # Preserve execution evidence inside the source tree before calculating the tree.
 ev_src=ROOT.parent/'evidence';ev_dst=ROOT/'release/evidence'
 if ev_dst.exists():shutil.rmtree(ev_dst)
 if ev_src.is_dir():shutil.copytree(ev_src,ev_dst,ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
 entries=source_entries();tree=tree_manifest(entries)
 # Add the newly-created tree files to source package.
 entries=source_entries()
 # Source provenance is stable for the package build.
 os.system(f"python3 '{ROOT/'scripts/release/generate_provenance.py'}' >/dev/null")
 entries=source_entries()
 source_path=delivery/f'PIGE360-{VERSION}-source.zip';source=make_zip(source_path,entries)
 # Reproducibility check: build from identical inputs a second time.
 with tempfile.TemporaryDirectory(prefix='pige360-repro-') as td:
  second=Path(td)/source_path.name;make_zip(second,entries);repro=sha(second)==source['sha256']
 if not repro:raise RuntimeError('ZIP source não reproduzível')
 self_prefix=['VERSION','README.md','CHANGELOG.md','SECURITY.md','LICENSE-NOTICE.md','.env.example','compose.yaml','compose.production.yaml','backend','apps','packages/api-sdk','packages/design-tokens','packages/ui','packages/offline-sync','packages/tenant-branding','infra','deploy/self-hosted','deploy/local','docs/deployment','docs/operations','docs/security','docs/user-guides','docs/api','docs/branding','docs/app-factory','docs/mobile','scripts/local','scripts/backup','scripts/restore','scripts/validation','release/artifacts','release/reports','release/toolchain-inventory.json','release/project-validation.json','release/secret-scan-report.json','release/PIGE360-'+VERSION+'-sbom.cdx.json']
 selfhost_path=delivery/f'PIGE360-{VERSION}-self-hosted.zip';selfhost=make_zip(selfhost_path,select_entries(self_prefix))
 wf_prefix=['.github/workflows','CI_CD_KIT_LOCAL','scripts/ci','scripts/release','scripts/desktop','scripts/mobile','scripts/oci','scripts/supply-chain','scripts/validation','docs/ci-cd','compose.yaml','compose.production.yaml','VERSION']
 workflows_path=delivery/f'PIGE360-{VERSION}-workflows-ci-cd.zip';workflows=make_zip(workflows_path,select_entries(wf_prefix))
 prelim=[source,selfhost,workflows]
 packages_json=ROOT/'release/packages-preliminary.json';packages_json.write_text(json.dumps(prelim,ensure_ascii=False,indent=2),encoding='utf-8')
 os.system(f"python3 '{ROOT/'scripts/release/generate-manifest.py'}' --packages-json '{packages_json}' --output 'release/PIGE360-{VERSION}-release-manifest-prepackage.json' >/dev/null")
 release_prefix=['VERSION','README.md','CHANGELOG.md','SECURITY.md','LICENSE-NOTICE.md','.env.example','docs','release/artifacts','release/reports','release/evidence','release/toolchain-inventory.json','release/project-validation.json','release/secret-scan-report.json','release/source-tree-manifest.json','release/final-tree.txt','release/PIGE360-'+VERSION+'-sbom.cdx.json','release/PIGE360-'+VERSION+'-source-provenance.intoto.json','release/PIGE360-'+VERSION+'-release-manifest-prepackage.json','docs/api','packages/api-sdk','CI_CD_KIT_LOCAL','.github/workflows','compose.yaml','compose.production.yaml']
 release_path=delivery/f'PIGE360-{VERSION}-release-bundle.zip'
 release_bundle=make_zip(release_path,select_entries(release_prefix),[(f'packages/{source_path.name}',source_path),(f'packages/{selfhost_path.name}',selfhost_path),(f'packages/{workflows_path.name}',workflows_path)])
 packages=[source,release_bundle,selfhost,workflows]
 package_subjects=[{'name':p['name'],'digest':{'sha256':p['sha256']}} for p in packages]
 subjects_file=ROOT/'release/package-subjects.json';subjects_file.write_text(json.dumps(package_subjects,ensure_ascii=False,indent=2),encoding='utf-8')
 final_manifest=delivery/f'PIGE360-{VERSION}-release-manifest.json'
 os.system(f"python3 '{ROOT/'scripts/release/generate-manifest.py'}' --packages-json '{ROOT/'release/packages-final.json'}' --output '{final_manifest}' >/dev/null") if False else None
 # Generate final manifest directly after writing package metadata.
 (ROOT/'release/packages-final.json').write_text(json.dumps(packages,ensure_ascii=False,indent=2),encoding='utf-8')
 import subprocess
 subprocess.run(['python3',str(ROOT/'scripts/release/generate-manifest.py'),'--packages-json',str(ROOT/'release/packages-final.json'),'--output',str(final_manifest)],check=True,capture_output=True,text=True)
 provenance=delivery/f'PIGE360-{VERSION}-release-provenance.intoto.json'
 subprocess.run(['python3',str(ROOT/'scripts/release/generate_provenance.py'),'--subjects-json',str(subjects_file),'--output',str(provenance)],check=True,capture_output=True,text=True)
 # Expose key evidence beside the ZIPs.
 copies=[ROOT/f'release/PIGE360-{VERSION}-sbom.cdx.json',ROOT/f'release/artifacts/oci/PIGE360-{VERSION}-images-oci.tar',ROOT/f'release/artifacts/oci/PIGE360-{VERSION}-images-digests.json',ROOT/f'release/artifacts/reports/PIGE360-{VERSION}-relatorio-evidencias.pdf',ROOT/'release/reports/test-report.json',ROOT/'release/reports/build-report.json',ROOT/'release/reports/local-ci-report.json',ROOT/'release/project-validation.json',ROOT/'docs/design/visual-regression-report.json']
 for src in copies:shutil.copy2(src,delivery/src.name)
 validation=validate_archives(packages);validation['source_reproducible']=repro;validation['generated_at']=datetime.now(timezone.utc).isoformat();validation_path=delivery/'archive-validation-report.json';validation_path.write_text(json.dumps(validation,ensure_ascii=False,indent=2),encoding='utf-8')
 if validation['status']!='passed':raise RuntimeError(validation)
 # Delivery checksums (excluding the checksum file itself).
 lines=[]
 for p in sorted(delivery.iterdir()):
  if p.is_file() and p.name!='SHA256SUMS':lines.append(f'{sha(p)}  {p.name}')
 (delivery/'SHA256SUMS').write_text('\n'.join(lines)+'\n',encoding='utf-8')
 # Validate checksum list.
 for line in lines:
  expected,name=line.split('  ',1);assert sha(delivery/name)==expected
 summary={'status':'passed','version':VERSION,'output_dir':str(delivery),'packages':packages,'source_reproducible':repro,'archive_validation':validation,'sha256s':str(delivery/'SHA256SUMS')}
 (delivery/'DELIVERY-SUMMARY.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
 # Include summary in checksums by regenerating once.
 lines=[]
 for p in sorted(delivery.iterdir()):
  if p.is_file() and p.name!='SHA256SUMS':lines.append(f'{sha(p)}  {p.name}')
 (delivery/'SHA256SUMS').write_text('\n'.join(lines)+'\n',encoding='utf-8')
 print(json.dumps({'status':'passed','output':str(delivery),'packages':[{k:p[k] for k in ['name','sha256','bytes','files']} for p in packages],'source_reproducible':repro,'files':len(list(delivery.iterdir()))},ensure_ascii=False))
if __name__=='__main__':main()
