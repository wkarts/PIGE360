#!/usr/bin/env python3
from __future__ import annotations
import argparse,hashlib,json
from datetime import datetime,timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
VERSION=(ROOT/'VERSION').read_text().strip()

def sha(path:Path)->str:return hashlib.sha256(path.read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser();p.add_argument('--packages-json');p.add_argument('--output',default=f'release/PIGE360-{VERSION}-release-manifest.json');a=p.parse_args()
 packages=json.loads(Path(a.packages_json).read_text()) if a.packages_json else []
 openapi=json.loads((ROOT/'docs/api/OPENAPI_REPORT.json').read_text())
 visual=json.loads((ROOT/'packages/visual-testing/baselines/visual-baseline-manifest.json').read_text())
 tests=json.loads((ROOT/'release/reports/test-report.json').read_text())
 build=json.loads((ROOT/'release/reports/build-report.json').read_text())
 backup=json.loads((ROOT/'release/artifacts/backup-restore/report.json').read_text())
 sbom=ROOT/f'release/PIGE360-{VERSION}-sbom.cdx.json'
 manifest={
  'schema_version':1,'product':'PIGE360','full_name':'PIGE360 — Plataforma Integrada de Gestão Educacional','version':VERSION,
  'generated_at':datetime.now(timezone.utc).isoformat(),'workspace':str(ROOT),'construction_mode':'local-only','network_used':False,
  'remote_operations':{'code_hosting':False,'clone_sync':False,'authentication':False,'push':False,'tags':False,'release':False,'registry':False,'deploy':False,'pull_request':False},
  'inputs':[{'name':'PROMPT_FINAL_COMPLETO_PIGE360_V8_LOCAL_SEM_REPOSITORIO.md','sha256':'33d177211b3cfd4b80a19a61f351d5bd02950003bf2cda1d448a369e6686bc27'},{'name':'PIGE360_BRANDING_COMPLETO.zip','sha256':'9cc110eddc20c82b7176580f0aff09f16471cb0650d4ba32a2fe059f3d76f2ef'}],
  'evidence':{'pytest_passed':tests.get('pytest_passed'),'local_checks':len(tests.get('checks',[])),'openapi_paths':openapi['paths'],'openapi_operations':openapi['operations'],'openapi_schemas':openapi['schemas'],'applications':13,'backend_api_paths':openapi['paths'],'compose_services':46,'workflows':15,'visual_screens':len({r['screen'] for r in visual['records']}),'screenshots':len(visual['records']),'backup_restore':backup['status'],'cross_tenant_leakage':backup['cross_tenant_leakage']},
  'build_status':build['builds'],
  'sbom':{'path':sbom.relative_to(ROOT).as_posix(),'sha256':sha(sbom),'format':'CycloneDX 1.6'},
  'oci':json.loads((ROOT/f'release/artifacts/oci/PIGE360-{VERSION}-images-digests.json').read_text()),
  'packages':packages,
  'integrations':[
    {'name':'PostgreSQL async','status':'contract_and_migrations','validated_real':False},
    {'name':'Redis/RabbitMQ/MinIO','status':'compose_and_contracts','validated_real':False},
    {'name':'Cloudflare','status':'not_configured','validated_real':False},
    {'name':'Mailcow','status':'not_configured','validated_real':False},
    {'name':'Evolution API','status':'not_configured','validated_real':False},
    {'name':'Fiscal SEFAZ/NFS-e','status':'not_homologated','validated_real':False},
    {'name':'GOV.BR','status':'not_configured_conditional','validated_real':False},
    {'name':'ICP-Brasil','status':'provider_contract_only','validated_real':False},
    {'name':'Play/App Store','status':'workflows_conditional_no_upload','validated_real':False},
  ],
  'known_input_issue':{'branding_sha256s_references_missing_files':4,'files':[f'10_SOURCE_REFERENCES/source-reference-{i:02d}.png' for i in range(1,5)]},
  'residual_risks_document':'docs/operations/RISK_REGISTER.md',
 }
 out=ROOT/a.output;out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps({'status':'generated','output':str(out),'packages':len(packages)},ensure_ascii=False))
if __name__=='__main__':main()
