#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import tomllib
from pathlib import Path
from typing import Any

import yaml

ROOT=Path(__file__).resolve().parents[2]
EXPECTED_APPS={'platform-console','branding-studio','tenant-download-center','tenant-admin-web','public-portal','family-app','teacher-app','student-app','admin-app','pos-app','kiosk-app','timeclock-app','desktop-admin'}
EXPECTED_WORKFLOWS={'00-ci.yml','05-pedagogy-attendance.yml','10-base-images.yml','20-application-images.yml','30-build-web.yml','31-build-desktop.yml','32-build-android.yml','33-build-ios.yml','34-build-tenant-apps.yml','40-security.yml','50-release.yml','51-recover-release.yml','60-deploy-saas.yml','61-self-hosted-bundle.yml','70-backup-restore-test.yml','80-dependency-maintenance.yml'}
EXPECTED_SERVICES=set('''pige360-api pige360-web pige360-platform-console pige360-branding-studio pige360-tenant-download-center pige360-app-factory-api pige360-worker-app-builds pige360-worker-app-distribution pige360-worker-visual-regression pige360-worker-default pige360-worker-high-priority pige360-worker-academic pige360-worker-pedagogy pige360-worker-attendance pige360-worker-finance pige360-worker-banking pige360-worker-fiscal pige360-worker-sales pige360-worker-hr pige360-worker-mail pige360-worker-notifications pige360-worker-documents pige360-worker-contracts pige360-worker-signatures pige360-worker-reports pige360-worker-integrations pige360-builder-linux pige360-builder-windows pige360-builder-macos pige360-builder-android pige360-builder-ios pige360-beat pige360-postgres-control pige360-postgres-tenants pige360-redis pige360-rabbitmq pige360-minio pige360-minio-init pige360-app-init pige360-clamav pige360-cloudflared-control pige360-cloudflared-tenants pige360-otel-collector pige360-prometheus pige360-grafana pige360-loki'''.split())
REQUIRED_MODULES={'foundation','tenancy','branding','app_factory','app_distribution','identity','authorization','people','students','guardians','employees','admissions','secretary','enrollment','academic','pedagogy','lesson_planning','class_attendance','finance','services','banking','sales','pos','canteen','inventory','procurement','assets','fiscal','hr','personnel','payroll','timekeeping','events','travel','notices','requests','workflows','communication','mail','contracts','documents','signatures','library','transportation','health','compliance','government_education','reporting','analytics','integrations','platform_operations'}

def add(checks:list[dict[str,Any]],name:str,ok:bool,detail:Any)->None:
 checks.append({'name':name,'status':'passed' if ok else 'failed','detail':detail})

def skip(checks:list[dict[str,Any]],name:str,detail:Any)->None:
 checks.append({'name':name,'status':'skipped','detail':detail})

def main()->int:
 parser=argparse.ArgumentParser();parser.add_argument('--security-only',action='store_true');parser.add_argument('--output');args=parser.parse_args();checks=[]
 version=(ROOT/'VERSION').read_text().strip();add(checks,'semantic-version',bool(re.fullmatch(r'\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?',version)),version)
 env=(ROOT/'.env.example').read_text();remote={k:re.search(rf'(?m)^{k}=(.*)$',env).group(1) for k in ['REMOTE_CI_ENABLED','REMOTE_REGISTRY_ENABLED','REMOTE_RELEASE_ENABLED','REMOTE_DEPLOY_ENABLED']};add(checks,'remote-disabled-default',all(v=='false' for v in remote.values()),remote)
 # Security-relevant selector and config checks.
 middleware=(ROOT/'backend/app/shared/security/middleware.py').read_text();add(checks,'tenant-selector-rejected','X-Tenant-ID' in middleware and 'tenant_id' in middleware,'hostname-only')
 add(checks,'no-font-files',not any(ROOT.rglob('*.ttf')) and not any(ROOT.rglob('*.otf')) and not any(ROOT.rglob('*.woff')) and not any(ROOT.rglob('*.woff2')),'font binaries absent')
 if not args.security_only:
  apps={p.name for p in (ROOT/'apps').iterdir() if p.is_dir()};add(checks,'applications',apps==EXPECTED_APPS,{'count':len(apps),'missing':sorted(EXPECTED_APPS-apps),'extra':sorted(apps-EXPECTED_APPS)})
  missing_source=[]
  for app in EXPECTED_APPS:
   for rel in ['src/App.vue','src-tauri/tauri.conf.json','package.json']:
    if not (ROOT/'apps'/app/rel).is_file():missing_source.append(f'{app}/{rel}')
  add(checks,'application-source-contracts',not missing_source,missing_source)
  stale_dist=[]
  for app in EXPECTED_APPS:
   dist=ROOT/'apps'/app/'dist'
   if dist.exists():
    text='\n'.join(x.read_text(encoding='utf-8',errors='ignore') for x in dist.rglob('*') if x.is_file() and x.stat().st_size < 2_000_000)
    if 'Colégio Horizonte' in text or 'BUILD-MANIFEST.json' in {x.name for x in dist.rglob('*') if x.is_file()}:
     stale_dist.append(app)
  add(checks,'no-obsolete-frontend-dist',not stale_dist,stale_dist)
  modules={p.name for p in (ROOT/'backend/app/modules').iterdir() if p.is_dir()};add(checks,'backend-modules',REQUIRED_MODULES<=modules,{'required':len(REQUIRED_MODULES),'present':len(REQUIRED_MODULES&modules),'missing':sorted(REQUIRED_MODULES-modules)})
  workflows={p.name for p in (ROOT/'.github/workflows').glob('*.yml')};add(checks,'workflows',workflows==EXPECTED_WORKFLOWS,{'count':len(workflows),'missing':sorted(EXPECTED_WORKFLOWS-workflows)})
  compose=yaml.safe_load((ROOT/'compose.yaml').read_text());services=set(compose.get('services',{}));add(checks,'compose-services',EXPECTED_SERVICES<=services,{'count':len(services),'missing':sorted(EXPECTED_SERVICES-services)})
  openapi=json.loads((ROOT/'docs/api/openapi.json').read_text());operations=[]
  for path,item in openapi.get('paths',{}).items():
   for method,op in item.items():
    if method.lower() in {'get','post','put','patch','delete','options','head'}:operations.append(op.get('operationId'))
  duplicate=sorted({x for x in operations if x and operations.count(x)>1})
  required_paths={
   '/api/v1/platform/tenants','/api/v1/platform/status','/api/v1/auth/login','/api/v1/people','/api/v1/students','/api/v1/enrollments',
   '/api/v1/teaching-plans','/api/v1/lesson-plans','/api/v1/class-sessions','/api/v1/attendance/risks','/api/v1/finance/contracts',
   '/api/v1/banking/accounts','/api/v1/products','/api/v1/sales','/api/v1/fiscal/simulate','/api/v1/hr/employment-contracts',
   '/api/v1/payroll/runs','/api/v1/timekeeping/me/entries','/api/v1/contracts','/api/v1/documents','/api/v1/events','/api/v1/service-requests',
   '/api/v1/library/items','/api/v1/transport/routes','/api/v1/government-education/exports','/api/v1/apps/catalog','/api/v1/public/context'
  }
  paths=set(openapi.get('paths',{}));missing_required=sorted(required_paths-paths)
  generic=[path for path in sorted(paths) if 'generic' in path.lower()]
  generic_ops=[op for op in operations if op and 'generic' in op.lower()]
  add(checks,'openapi-semantic-contract',not duplicate and not missing_required and not generic and not generic_ops,{'paths':len(paths),'operations':len(operations),'duplicates':duplicate,'missing_required':missing_required,'generic_paths':generic,'generic_operations':generic_ops})
  visual=json.loads((ROOT/'packages/visual-testing/baselines/visual-baseline-manifest.json').read_text());add(checks,'visual-evidence',len({r['screen'] for r in visual['records']})==40 and len(visual['records'])>=100,{'screens':len({r['screen'] for r in visual['records']}),'screenshots':len(visual['records'])})
  ref=json.loads((ROOT/'docs/design/reference-assets/manifest.json').read_text());add(checks,'reference-inventory',ref.get('assets_count',0)>=100,{'assets':ref.get('assets_count'),'known_issue':ref.get('known_source_integrity_issue')})
  # Parse every local declarative file.
  parse_errors=[]
  for p in ROOT.rglob('*.json'):
   if any(x in p.parts for x in {'node_modules','.pytest_cache'}):continue
   try:json.loads(p.read_text(encoding='utf-8'))
   except Exception as e:parse_errors.append(f'{p.relative_to(ROOT)}: {e}')
  for p in list(ROOT.rglob('*.yaml'))+list(ROOT.rglob('*.yml')):
   try:yaml.safe_load(p.read_text(encoding='utf-8'))
   except Exception as e:parse_errors.append(f'{p.relative_to(ROOT)}: {e}')
  for p in ROOT.rglob('*.toml'):
   try:tomllib.loads(p.read_text(encoding='utf-8'))
   except Exception as e:parse_errors.append(f'{p.relative_to(ROOT)}: {e}')
  add(checks,'declarative-syntax',not parse_errors,parse_errors[:20])
  critical=[]
  for p in (ROOT/'backend/app').rglob('*.py'):
   text=p.read_text(encoding='utf-8')
   if re.search(r'\b(TODO|FIXME|HACK)(?:\([^)]+\))?\s*:',text):critical.append(p.relative_to(ROOT).as_posix())
  add(checks,'no-critical-todos',not critical,critical)
  kit=json.loads((ROOT/'CI_CD_KIT_LOCAL/manifest.json').read_text());add(checks,'ci-cd-kit',len(kit.get('files',[]))>=16 and kit.get('remote_execution') is False,{'files':len(kit.get('files',[]))})
  oci_path=ROOT/f'release/artifacts/oci/PIGE360-{version}-images-digests.json'
  if oci_path.is_file():
   try:
    oci=json.loads(oci_path.read_text())
    add(checks,'oci-structural',len(oci.get('images',[]))>=12 and oci.get('runtime_build_executed') is False,{'images':len(oci.get('images',[])),'runtime_build':oci.get('runtime_build_executed')})
   except Exception as exc:
    add(checks,'oci-structural',False,{'path':oci_path.relative_to(ROOT).as_posix(),'error':str(exc)})
  else:
   skip(checks,'oci-structural',{'path':oci_path.relative_to(ROOT).as_posix(),'reason':'artefato OCI não gerado neste workspace de fonte local'})
 failures=[c for c in checks if c['status']=='failed'];result={'status':'passed' if not failures else 'failed','version':version,'checks':checks,'failures':failures}
 if args.output:
  out=Path(args.output);out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
 print(json.dumps(result,ensure_ascii=False,indent=2));return 0 if not failures else 1
if __name__=='__main__':raise SystemExit(main())
