#!/usr/bin/env python3
from __future__ import annotations
import argparse,hashlib,json,uuid
from datetime import datetime,timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];VERSION=(ROOT/'VERSION').read_text().strip()
def sha(p:Path):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser();p.add_argument('--subjects-json');p.add_argument('--output',default=f'release/PIGE360-{VERSION}-source-provenance.intoto.json');a=p.parse_args()
 subjects=json.loads(Path(a.subjects_json).read_text()) if a.subjects_json else [{'name':'pige360-source-tree','digest':{'sha256':sha(ROOT/'release/source-tree-manifest.json')}}]
 now=datetime.now(timezone.utc).isoformat()
 statement={'_type':'https://in-toto.io/Statement/v1','subject':subjects,'predicateType':'https://slsa.dev/provenance/v1','predicate':{'buildDefinition':{'buildType':'https://pige360.local/build/v8','externalParameters':{'version':VERSION,'mode':'local-only','remote_ci_enabled':False,'remote_registry_enabled':False,'remote_release_enabled':False,'remote_deploy_enabled':False},'internalParameters':{'workspace':str(ROOT),'vcs_commit':None,'network_used':False},'resolvedDependencies':[{'uri':'file:PROMPT_FINAL_COMPLETO_PIGE360_V8_LOCAL_SEM_REPOSITORIO.md','digest':{'sha256':'33d177211b3cfd4b80a19a61f351d5bd02950003bf2cda1d448a369e6686bc27'}},{'uri':'file:PIGE360_BRANDING_COMPLETO.zip','digest':{'sha256':'9cc110eddc20c82b7176580f0aff09f16471cb0650d4ba32a2fe059f3d76f2ef'}}]},'runDetails':{'builder':{'id':'local://openai/gpt-5.6-pro'},'metadata':{'invocationId':str(uuid.uuid5(uuid.NAMESPACE_URL,'pige360:'+VERSION+':local-v8')),'startedOn':now,'finishedOn':now},'byproducts':[{'name':'release/reports/local-ci-report.json','digest':{'sha256':sha(ROOT/'release/reports/local-ci-report.json')}},{'name':'release/toolchain-inventory.json','digest':{'sha256':sha(ROOT/'release/toolchain-inventory.json')}}]}}}
 out=ROOT/a.output if not Path(a.output).is_absolute() else Path(a.output);out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(statement,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps({'status':'generated','output':str(out),'subjects':len(subjects)},ensure_ascii=False))
if __name__=='__main__':main()
