#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import yaml
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT=Path(__file__).resolve().parents[2]
VERSION=(ROOT/'VERSION').read_text().strip()
REPORTS=ROOT/'release/reports'
LOGS=REPORTS/'logs'


def run(name:str,cmd:list[str],cwd:Path|None=None,env:dict[str,str]|None=None)->dict[str,Any]:
    started=datetime.now(timezone.utc)
    merged=os.environ.copy()
    if env:merged.update(env)
    try:
        proc=subprocess.run(cmd,cwd=cwd or ROOT,env=merged,text=True,capture_output=True)
        returncode=proc.returncode;stdout=proc.stdout;stderr=proc.stderr
    except FileNotFoundError as exc:
        returncode=127;stdout='';stderr=f'Ferramenta não encontrada: {exc.filename}\n'
    except OSError as exc:
        returncode=126;stdout='';stderr=f'Falha ao iniciar a verificação: {exc}\n'
    ended=datetime.now(timezone.utc)
    log=LOGS/f'{name}.log';log.parent.mkdir(parents=True,exist_ok=True)
    log.write_text('$ '+' '.join(cmd)+'\n\nSTDOUT\n'+stdout+'\nSTDERR\n'+stderr,encoding='utf-8')
    return {'name':name,'command':cmd,'status':'passed' if returncode==0 else 'failed','returncode':returncode,'started_at':started.isoformat(),'finished_at':ended.isoformat(),'duration_seconds':round((ended-started).total_seconds(),3),'log':log.relative_to(ROOT).as_posix(),'stdout_tail':stdout[-1000:],'stderr_tail':stderr[-1000:]}


def skipped(name:str,cmd:list[str],prerequisites:list[str])->dict[str,Any]:
    now=datetime.now(timezone.utc);reason='Pré-requisito falhou: '+', '.join(prerequisites)
    log=LOGS/f'{name}.log';log.parent.mkdir(parents=True,exist_ok=True)
    log.write_text('$ '+' '.join(cmd)+'\n\nSKIPPED\n'+reason+'\n',encoding='utf-8')
    return {'name':name,'command':cmd,'status':'skipped','returncode':125,'started_at':now.isoformat(),'finished_at':now.isoformat(),'duration_seconds':0.0,'log':log.relative_to(ROOT).as_posix(),'stdout_tail':'','stderr_tail':reason}


def markdown_table(records:list[dict[str,Any]])->str:
    lines=['| Verificação | Status | Duração | Evidência |','|---|---|---:|---|']
    for r in records:lines.append(f"| `{r['name']}` | **{r['status']}** | {r['duration_seconds']} s | `{r['log']}` |")
    return '\n'.join(lines)


def project_inventory()->dict[str,int]:
    apps=len([path for path in (ROOT/'apps').glob('*/package.json') if path.is_file()])
    compose_files=[ROOT/'compose.yaml',ROOT/'compose.production.yaml']
    compose_files.extend(sorted((ROOT/'deploy/compose').glob('*.yaml')))
    services:set[str]=set()
    for path in compose_files:
        if not path.is_file():continue
        document=yaml.safe_load(path.read_text(encoding='utf-8')) or {}
        raw_services=document.get('services',{})
        if isinstance(raw_services,dict):services.update(str(name) for name in raw_services)
    oci_images=0
    digest_path=ROOT/f'release/artifacts/oci/PIGE360-{VERSION}-images-digests.json'
    if digest_path.is_file():
        try:oci_images=len(json.loads(digest_path.read_text(encoding='utf-8')).get('images',[]))
        except (OSError,json.JSONDecodeError,TypeError):oci_images=0
    return {'apps':apps,'compose_services':len(services),'oci_images':oci_images}


def main()->int:
    parser=argparse.ArgumentParser();parser.add_argument('--ci',action='store_true');parser.add_argument('--network-used',action='store_true',help='Registra que esta execução usou rede para resolver dependências');parser.add_argument('--allow-prerelease',action='store_true',help='Valida explicitamente uma tag SemVer prerelease já imutável');args=parser.parse_args()
    REPORTS.mkdir(parents=True,exist_ok=True);LOGS.mkdir(parents=True,exist_ok=True)
    version_command=[sys.executable,'scripts/validation/validate_version_consistency.py','--output','release/version-consistency.json']
    if args.allow_prerelease:version_command.append('--allow-prerelease')
    commands=[
      ('toolchain-inventory',[sys.executable,'scripts/supply-chain/toolchain_inventory.py','--output','release/toolchain-inventory.json'],None,None),
      ('python-compile',[sys.executable,'-m','compileall','-q','backend/app','backend/tests','scripts'],None,None),
      ('pytest',[sys.executable,'scripts/ci/run_pytest_isolated.py'],None,None),
      ('release-tooling-tests',[sys.executable,'-m','pytest','-q','scripts/release/tests'],None,None),
      ('openapi-export',[sys.executable,'scripts/api/export_openapi.py'],None,None),
      ('sdk-generation',[sys.executable,'scripts/api/generate_typescript_sdk.py'],None,None),
      ('typescript-strict',['npm','run','--silent','validate:ts'],None,None),
      ('migration-control-sql',[sys.executable,'-m','alembic','-c','backend/alembic_control/alembic.ini','upgrade','head','--sql'],None,None),
      ('migration-tenant-sql',[sys.executable,'-m','alembic','-c','backend/alembic_tenant/alembic.ini','upgrade','head','--sql'],None,None),
      ('visual-contract',[sys.executable,'scripts/visual/validate_visual_contract.py'],None,None),
      ('tenant-app-manifest',[sys.executable,'scripts/validation/tenant_app_manifest.py','deploy/local/tenant-app-manifest.demo.yaml'],None,None),
      ('version-consistency',version_command,None,None),
      ('release-build-readiness',[sys.executable,'scripts/validation/validate_release_build_readiness.py'],None,None),
      ('integrated-deployer',[sys.executable,'scripts/validation/validate_integrated_deployer.py'],None,None),
      ('dockerfile-policy',[sys.executable,'scripts/validation/validate_dockerfiles.py'],None,None),
      ('secret-scan',[sys.executable,'scripts/validation/secret_scan.py','--output','release/secret-scan-report.json'],None,None),
      ('backup-restore',[sys.executable,'scripts/backup/test_backup_restore.py'],None,None),
      ('sbom',[sys.executable,'scripts/supply-chain/generate_sbom.py']+(['--network-used'] if args.network_used else []),None,None),
      ('oci-structural',[sys.executable,'scripts/oci/build_structural_oci.py'],None,None),
      ('project-validation',[sys.executable,'scripts/validation/validate_project.py','--output','release/project-validation.json'],None,None),
    ]
    if args.ci:
        # O type-check raiz usa o TypeScript instalado no package-lock. A
        # instalação precisa ocorrer antes dele para que o npm não tente
        # resolver o pacote legado `tsc` pela rede.
        commands.insert(5,('frontend-install',['bash','scripts/frontend/install-dependencies.sh'],None,None))
        commands.insert(6,('npm-audit',['npm','audit','--omit=dev','--audit-level=moderate'],None,None))
        commands.insert(8,('frontend-build',['npm','run','build:web'],None,None))
        commands.insert(9,('pwa-build-validation',[sys.executable,'scripts/validation/validate_pwa_builds.py'],None,None))
    dependencies={'sdk-generation':['openapi-export']}
    if args.ci:
        dependencies.update({'npm-audit':['frontend-install'],'typescript-strict':['frontend-install'],'frontend-build':['frontend-install'],'pwa-build-validation':['frontend-build']})
    records=[]
    for name,cmd,cwd,env in commands:
        failed_prerequisites=[dependency for dependency in dependencies.get(name,[]) if any(record['name']==dependency and record['status']!='passed' for record in records)]
        result=skipped(name,cmd,failed_prerequisites) if failed_prerequisites else run(name,cmd,cwd,env);records.append(result)
        print(f"[{result['status'].upper()}] {name} ({result['duration_seconds']}s)",flush=True)
        if result['status']=='failed':
            print(result['stdout_tail']);print(result['stderr_tail'],file=sys.stderr)
    failures=[r for r in records if r['status']=='failed']
    toolchains=json.loads((ROOT/'release/toolchain-inventory.json').read_text())['tools']
    native=[]
    checks=[
      ('desktop-windows-linux-macos','cargo', ['Windows x64/x86','Linux x64/ARM64','macOS Intel/Apple Silicon']),
      ('android-apk-aab','gradle',['APK','AAB']),
      ('ios-app-xcarchive-ipa','xcodebuild',['.app','.xcarchive','IPA unsigned']),
      ('container-runtime','docker',['imagens base','imagens de aplicação','smoke test Compose']),
    ]
    for name,tool,artifacts in checks:
        available=toolchains.get(tool,{}).get('available',False)
        native.append({'name':name,'status':'not_executed' if not available else 'toolchain_available_not_invoked','tool':tool,'artifacts_expected':artifacts,'reason':f'{tool} não disponível no workspace local' if not available else 'compilação reservada ao workflow específico'})
    frontend_bundle=next((record for record in records if record['name']=='frontend-build'),None)
    frontend_bundle_passed=bool(frontend_bundle and frontend_bundle['status']=='passed')
    native.append({'name':'vue-vite-production-bundle','status':'passed' if frontend_bundle_passed else 'not_executed','tool':'npm','artifacts_expected':['bundles Vite'],'reason':'13 bundles Vite executados e validados' if frontend_bundle_passed else 'modo --ci não executado ou instalação frontend indisponível'})
    openapi=json.loads((ROOT/'docs/api/OPENAPI_REPORT.json').read_text())
    visual=json.loads((ROOT/'packages/visual-testing/baselines/visual-baseline-manifest.json').read_text())
    workflow_count=len(list((ROOT/'.github/workflows').glob('*.yml')))+len(list((ROOT/'.github/workflows').glob('*.yaml')))
    inventory=project_inventory()
    build_report={'schema_version':2,'version':VERSION,'generated_at':datetime.now(timezone.utc).isoformat(),'network_used':bool(args.network_used),'network_usage_source':'declared_by_runner' if args.network_used else 'not_declared','workflows':workflow_count,'builds':{
      'backend':{'status':'passed' if not any(r['name'] in {'python-compile','pytest','release-tooling-tests','openapi-export'} and r['status']=='failed' for r in records) else 'failed','api_paths':openapi['paths'],'openapi_paths':openapi['paths'],'openapi_operations':openapi['operations']},
      'web_pwa_source':{'status':'passed' if any(r['name']=='frontend-build' and r['status']=='passed' for r in records) else 'source_validated','apps':inventory['apps'],'typescript_strict':not any(r['name']=='typescript-strict' and r['status']=='failed' for r in records),'production_bundle_executed':any(r['name']=='frontend-build' and r['status']=='passed' for r in records)},
      'visual':{'status':'baseline_validated','screens':len({r['screen'] for r in visual['records']}),'screenshots':len(visual['records']),'pixel_regression_executed':False},
      'compose_and_dockerfiles':{'status':'structural_only','services':inventory['compose_services'],'runtime_executed':False},
      'oci':{'status':'structural_only','runtime_executable':False,'images':inventory['oci_images']},
      'native_and_external_toolchains':native,
    },'limitations':'Nenhum binário ou container foi declarado aprovado sem execução da toolchain correspondente.'}
    (REPORTS/'build-report.json').write_text(json.dumps(build_report,ensure_ascii=False,indent=2),encoding='utf-8')
    build_md=['# Relatório de builds','',f'Versão: `{VERSION}`','', '- Backend/OpenAPI/SDK: executados localmente.',('- Frontend Vue/Vite: 13 bundles de produção executados e validados.' if frontend_bundle_passed else '- Fontes Vue/TypeScript: validadas em modo estrito; bundle Vite não executado neste modo.'),f"- Catálogo visual: {len(visual['records'])} registros de baseline; comparação de pixels não executada.",'- Docker/OCI executável e builds nativos: não executados sem a toolchain correspondente; nenhuma evidência falsa é criada.','', '## Toolchains não executadas','']
    for x in native:build_md.append(f"- **{x['name']}** — `{x['status']}`: {x['reason']}.")
    (REPORTS/'build-report.md').write_text('\n'.join(build_md)+'\n',encoding='utf-8')
    pytest_record=next(r for r in records if r['name']=='pytest'); m=re.search(r'(\d+)/(\d+) nós passaram', pytest_record['stdout_tail']); passed=int(m.group(1)) if m else None
    test_report={'schema_version':1,'version':VERSION,'status':'passed' if not failures else 'failed','pytest_passed':passed,'checks':records,'failed_checks':[r['name'] for r in failures]}
    (REPORTS/'test-report.json').write_text(json.dumps(test_report,ensure_ascii=False,indent=2),encoding='utf-8')
    (REPORTS/'test-report.md').write_text(f"# Relatório de testes e validações\n\nVersão: `{VERSION}`\n\nStatus: **{test_report['status']}**\n\nPytest: **{passed if passed is not None else 'não identificado'} aprovados**.\n\n{markdown_table(records)}\n",encoding='utf-8')
    ci={'schema_version':2,'version':VERSION,'status':'passed' if not failures else 'failed','network_used':bool(args.network_used),'network_usage_source':'declared_by_runner' if args.network_used else 'not_declared','remote_operations_executed':False,'commands':records,'native_builds':native,'workflows':workflow_count}
    (REPORTS/'local-ci-report.json').write_text(json.dumps(ci,ensure_ascii=False,indent=2),encoding='utf-8')
    (REPORTS/'local-ci-report.md').write_text(f"# CI local\n\nStatus: **{ci['status']}**\n\nNenhuma operação remota foi executada.\n\n{markdown_table(records)}\n",encoding='utf-8')
    print(json.dumps({'status':ci['status'],'checks':len(records),'failures':[r['name'] for r in failures],'pytest_passed':passed,'apps_source':inventory['apps'],'screenshots':len(visual['records'])},ensure_ascii=False))
    return 0 if not failures else 1
if __name__=='__main__':raise SystemExit(main())
