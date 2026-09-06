#!/usr/bin/env python3
from __future__ import annotations
import argparse,hashlib,json,os,shutil,stat,subprocess,sys,tempfile,time,zipfile
from datetime import datetime,timezone
from pathlib import Path,PurePosixPath

ROOT=Path(__file__).resolve().parents[2]
VERSION=(ROOT/'VERSION').read_text().strip()
DELIVERY=Path('/mnt/data/PIGE360_V8_LOCAL_DELIVERY')
EXCLUDED_PARTS={'.git','.continua-ai','node_modules','dist','target','build','coverage','.toolchains','__pycache__','.pytest_cache','.mypy_cache','.ruff_cache','.venv','venv','runtime-data','runtime-secrets','backups','release-output'}
EXCLUDED_SUFFIX={'.pyc','.pyo','.tsbuildinfo','.key','.pem','.p8','.p12','.pfx','.jks','.keystore','.crt','.cer','.der','.mobileprovision','.provisionprofile'}
EXCLUDED_NAMES={'.env','id_rsa','id_ed25519','.DS_Store','Thumbs.db','CHECKPOINT_MANIFEST.json'}
SOURCE_RELEASE_ALLOWLIST={'release/version-consistency.json'}
DELIVERY_MARKER='.pige360-delivery-root.json'
GENERATED_OPERATION_DOCS={
 'docs/operations/BEFORE_AFTER_REPORT.json','docs/operations/BEFORE_AFTER_REPORT.md',
 'docs/operations/FINAL_LOCAL_VALIDATION.md','docs/operations/LOCAL_EXECUTION_REPORT.md',
}
EXTERNAL_EVIDENCE_SUFFIXES={'.csv','.html','.json','.log','.md','.txt','.xml'}
EXTERNAL_EVIDENCE_MAX_FILE_BYTES=25*1024*1024
EXTERNAL_EVIDENCE_MAX_TOTAL_BYTES=100*1024*1024
REQUIRED_CI_COMMANDS={
 'toolchain-inventory','python-compile','pytest','release-tooling-tests','openapi-export','sdk-generation','frontend-install','npm-audit',
 'typescript-strict','frontend-build','pwa-build-validation','migration-control-sql',
 'migration-tenant-sql','visual-contract','tenant-app-manifest','version-consistency','release-build-readiness','dockerfile-policy',
 'secret-scan','backup-restore','sbom','oci-structural','project-validation',
}
SELF_HOSTED_PREFIXES=[
 'VERSION','README.md','CHANGELOG.md','SECURITY.md','LICENSE-NOTICE.md',
 '.env.example','.dockerignore','Makefile','package.json','package-lock.json',
 'tsconfig.validation.json','compose.yaml','compose.production.yaml',
 'backend','apps','packages','rust','types','infra','deploy','deployments','scripts',
 'docs/deployment','docs/operations','docs/security','docs/user-guides','docs/api',
 'docs/branding','docs/app-factory','docs/mobile',
]

def sha(path:Path)->str:
 h=hashlib.sha256()
 with path.open('rb') as f:
  for chunk in iter(lambda:f.read(1024*1024),b''):h.update(chunk)
 return h.hexdigest()
def allowed(path:Path)->bool:
 if not path.is_file() or path.is_symlink():return False
 rel=path.relative_to(ROOT)
 if any(p in EXCLUDED_PARTS for p in rel.parts):return False
 if rel.parts[:2]==('release','output'):return False
 if rel.parts[:2]==('release','.openapi-runtime'):return False
 if path.name in EXCLUDED_NAMES:return False
 if path.name.startswith('.env.') and path.name!='.env.example':return False
 if path.suffix.lower() in EXCLUDED_SUFFIX:return False
 return True
def source_entries(*,include_release_generated:bool=False):
 result=[]
 for p in sorted(ROOT.rglob('*')):
  if not allowed(p):continue
  arc=p.relative_to(ROOT).as_posix()
  if not include_release_generated and arc.startswith('release/') and arc not in SOURCE_RELEASE_ALLOWLIST:continue
  result.append((arc,p))
 return result

def read_object(path:Path)->dict:
 if not path.is_file():raise RuntimeError(f'evidência obrigatória ausente: {path.relative_to(ROOT) if path.is_relative_to(ROOT) else path}')
 try:value=json.loads(path.read_text(encoding='utf-8'))
 except (UnicodeDecodeError,json.JSONDecodeError) as exc:raise RuntimeError(f'evidência JSON inválida: {path}: {exc}') from exc
 if not isinstance(value,dict):raise RuntimeError(f'evidência JSON deve conter objeto: {path}')
 return value

def delivery_identity(path:Path)->str:
 stat_result=path.stat()
 return hashlib.sha256(f'{stat_result.st_dev}:{stat_result.st_ino}'.encode()).hexdigest()

def acquire_delivery_lock(raw:Path):
 delivery=raw.expanduser().resolve()
 if delivery==Path('/') or not delivery.name:raise RuntimeError(f'diretório de entrega perigoso recusado: {delivery}')
 delivery.parent.mkdir(parents=True,exist_ok=True)
 lock_path=delivery.with_name(f'.{delivery.name}.package.lock')
 handle=lock_path.open('a+b')
 try:
  if os.name=='nt':
   import msvcrt
   handle.seek(0,os.SEEK_END)
   if handle.tell()==0:handle.write(b'\0');handle.flush()
   handle.seek(0);msvcrt.locking(handle.fileno(),msvcrt.LK_NBLCK,1)
  else:
   import fcntl
   fcntl.flock(handle.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
 except OSError as exc:
  handle.close()
  raise RuntimeError(f'outro empacotamento já usa o diretório de entrega: {delivery}') from exc
 handle.seek(0);handle.truncate();handle.write(json.dumps({'pid':os.getpid(),'started_at':datetime.now(timezone.utc).isoformat(),'delivery':str(delivery)},ensure_ascii=False).encode()+b'\n');handle.flush();os.fsync(handle.fileno())
 return handle

def prepare_delivery(raw:Path,*,root:Path=ROOT)->Path:
 raw=raw.expanduser()
 if raw.is_symlink():raise RuntimeError(f'diretório de entrega não pode ser link simbólico: {raw}')
 delivery=raw.resolve();project=root.resolve()
 if delivery==Path('/') or delivery==project or project.is_relative_to(delivery):
  raise RuntimeError(f'diretório de entrega perigoso recusado: {delivery}')
 if delivery.is_relative_to(project) and not delivery.is_relative_to(project/'release/output'):
  raise RuntimeError(f'dentro do projeto, use somente release/output: {delivery}')
 if delivery.exists():
  if not delivery.is_dir():raise RuntimeError(f'saída existente não é diretório: {delivery}')
  marker=delivery/DELIVERY_MARKER
  marker_data=read_object(marker) if marker.is_file() and not marker.is_symlink() else {}
  if marker_data.get('product')!='PIGE360' or marker_data.get('managed_by')!='package_local.py' or marker_data.get('directory_identity')!=delivery_identity(delivery):
   raise RuntimeError(f'diretório existente sem marcador de entrega; remoção recusada: {delivery}')
  shutil.rmtree(delivery)
 delivery.mkdir(parents=True)
 (delivery/DELIVERY_MARKER).write_text(json.dumps({'schema_version':1,'product':'PIGE360','managed_by':'package_local.py','directory_identity':delivery_identity(delivery)},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 return delivery

def parse_time(value:str)->datetime:
 try:parsed=datetime.fromisoformat(value.replace('Z','+00:00'))
 except (AttributeError,ValueError) as exc:raise RuntimeError(f'data de evidência inválida: {value!r}') from exc
 if parsed.tzinfo is None:raise RuntimeError(f'data de evidência sem timezone: {value!r}')
 return parsed

def final_secret_scan()->dict:
 output=ROOT/'release/secret-scan-report.json'
 process=subprocess.run(
  [sys.executable,str(ROOT/'scripts/validation/secret_scan.py'),'--root',str(ROOT),'--project-version',VERSION,'--output',str(output)],
  check=False,capture_output=True,text=True,
 )
 if process.returncode!=0:raise RuntimeError(f'varredura final de segredos falhou:\n{process.stdout[-2000:]}\n{process.stderr[-2000:]}')
 return read_object(output)

def validate_release_evidence(*,source_candidate:bool=False)->dict:
 ci=read_object(ROOT/'release/reports/local-ci-report.json')
 tests=read_object(ROOT/'release/reports/test-report.json')
 builds=read_object(ROOT/'release/reports/build-report.json')
 version=read_object(ROOT/'release/version-consistency.json')
 project=read_object(ROOT/'release/project-validation.json')
 secrets=read_object(ROOT/'release/secret-scan-report.json')
 openapi=read_object(ROOT/'docs/api/OPENAPI_REPORT.json')
 before_after=read_object(ROOT/'docs/operations/BEFORE_AFTER_REPORT.json')
 sbom_path=ROOT/f'release/PIGE360-{VERSION}-sbom.cdx.json';sbom=read_object(sbom_path)
 errors=[]
 for label,report in [('CI local',ci),('testes',tests),('consistência de versão',version),('validação do projeto',project),('segredos',secrets)]:
  if report.get('status')!='passed':errors.append(f'{label}: status={report.get("status")!r}')
 for label,report in [('CI local',ci),('testes',tests),('builds',builds),('consistência de versão',version),('validação do projeto',project),('segredos',secrets)]:
  if report.get('version')!=VERSION:errors.append(f'{label}: versão {report.get("version")!r} != {VERSION!r}')
 commands=ci.get('commands') if isinstance(ci.get('commands'),list) else []
 command_by_name={item.get('name'):item for item in commands if isinstance(item,dict) and item.get('name')}
 missing_commands=sorted(REQUIRED_CI_COMMANDS-set(command_by_name))
 failed_commands=sorted(name for name,item in command_by_name.items() if item.get('status')!='passed')
 if missing_commands:errors.append(f'CI sem comandos obrigatórios: {missing_commands}')
 if failed_commands:errors.append(f'CI contém comandos não aprovados: {failed_commands}')
 for item in commands:
  if not isinstance(item,dict):continue
  log=item.get('log')
  if not isinstance(log,str) or not log or '..' in PurePosixPath(log).parts or not (ROOT/log).is_file():
   errors.append(f'log ausente/inválido para {item.get("name")}: {log!r}')
 if not isinstance(tests.get('pytest_passed'),int) or tests.get('pytest_passed',0)<=0:errors.append('relatório de testes não registra casos pytest aprovados')
 if tests.get('failed_checks') not in (None,[]):errors.append(f'relatório de testes contém falhas: {tests.get("failed_checks")}')
 web=builds.get('builds',{}).get('web_pwa_source',{})
 backend=builds.get('builds',{}).get('backend',{})
 if backend.get('status')!='passed':errors.append(f'build backend não aprovado: {backend.get("status")!r}')
 if web.get('status')!='passed' or web.get('production_bundle_executed') is not True:errors.append('13 bundles Web/PWA não foram executados e aprovados')
 if version.get('stable_semver') is not True or version.get('product_prereleases') not in (None,[]):errors.append('versão final não é SemVer estável')
 if secrets.get('findings') not in (None,[]) or not isinstance(secrets.get('scanned_files'),int) or secrets.get('scanned_files',0)<=0:errors.append('varredura final de segredos é vazia ou contém achados')
 if openapi.get('version')!=VERSION:errors.append(f'OpenAPI versão {openapi.get("version")!r} != {VERSION!r}')
 if openapi.get('duplicate_operation_ids') not in (None,[]):errors.append('OpenAPI contém operationId duplicado')
 summary=before_after.get('summary',{})
 if summary.get('preservation_status')!='passed' or summary.get('removed')!=0:errors.append('relatório antes/depois não comprova preservação integral')
 if sbom.get('bomFormat')!='CycloneDX' or sbom.get('specVersion')!='1.6' or sbom.get('metadata',{}).get('component',{}).get('version')!=VERSION:errors.append('SBOM ausente, incompatível ou de outra versão')
 sbom_properties={item.get('name'):item.get('value') for item in sbom.get('properties',[]) if isinstance(item,dict) and item.get('name')}
 try:
  cargo_locks=int(sbom_properties.get('pige360:cargo-lockfiles','-1'));cargo_expected=int(sbom_properties.get('pige360:cargo-lockfiles-expected','-1'))
 except (TypeError,ValueError):cargo_locks=cargo_expected=-1
 cargo_complete=sbom_properties.get('pige360:cargo-resolution')=='cargo-lock' and cargo_expected>0 and cargo_locks==cargo_expected
 cargo_explicitly_unbuilt=source_candidate and sbom_properties.get('pige360:cargo-resolution')=='manifest-only' and cargo_expected>0 and cargo_locks==0
 if not cargo_complete and not cargo_explicitly_unbuilt:
  errors.append(f'SBOM Rust não está totalmente resolvido por Cargo.lock: {cargo_locks}/{cargo_expected}')
 verify=subprocess.run(
  [sys.executable,str(ROOT/'scripts/release/generate_before_after_report.py'),'--current-dir',str(ROOT),'--json-output',str(ROOT/'docs/operations/BEFORE_AFTER_REPORT.json'),'--verify-current'],
  check=False,capture_output=True,text=True,
 )
 if verify.returncode!=0:errors.append(f'relatório antes/depois está desatualizado: {verify.stdout[-1000:]} {verify.stderr[-1000:]}')
 finished=[]
 for item in commands:
  if isinstance(item,dict) and item.get('finished_at'):finished.append(parse_time(item['finished_at']))
 if not finished:errors.append('CI não registra horários de término')
 else:
  latest_source=max(((p.stat().st_mtime,arc) for arc,p in source_entries() if arc not in GENERATED_OPERATION_DOCS and not arc.startswith('release/')),default=(0.0,''))
  latest_ci=max(value.timestamp() for value in finished)
  if latest_source[0]>latest_ci+1.0:errors.append(f'evidência de CI anterior ao fonte atual: {latest_source[1]}')
 required_assets=[
  ROOT/'release/artifacts/backup-restore/report.json',
  ROOT/f'release/artifacts/oci/PIGE360-{VERSION}-images-oci.tar',
  ROOT/f'release/artifacts/oci/PIGE360-{VERSION}-images-digests.json',
 ]
 missing_assets=[str(path.relative_to(ROOT)) for path in required_assets if not path.is_file()]
 if missing_assets:errors.append(f'artefatos estruturais obrigatórios ausentes: {missing_assets}')
 else:
  backup=read_object(required_assets[0]);oci=read_object(required_assets[2]);oci_tar=required_assets[1]
  if backup.get('status')!='passed':errors.append(f'backup/restore sintético não aprovado: {backup.get("status")!r}')
  if oci.get('version')!=VERSION:errors.append(f'OCI estrutural versão {oci.get("version")!r} != {VERSION!r}')
  recorded_oci_hash=oci.get('bundle',{}).get('sha256')
  if not recorded_oci_hash or sha(oci_tar)!=recorded_oci_hash:errors.append('hash do bundle OCI estrutural diverge do relatório')
 stale=[]
 for path in sorted((ROOT/'release/artifacts').rglob('PIGE360-*')):
  if path.is_file() and not path.name.startswith(f'PIGE360-{VERSION}-') and not path.name.startswith(f'PIGE360-v{VERSION}-'):
   stale.append(path.relative_to(ROOT).as_posix())
 if stale:errors.append(f'artefatos de outra versão presentes na árvore: {stale[:20]}')
 if errors:raise RuntimeError('gates finais de evidência recusaram a entrega:\n- '+'\n- '.join(errors))
 return {
  'status':'partial' if source_candidate else 'passed','version':VERSION,'commands':len(commands),
  'pytest_passed':tests['pytest_passed'],'secret_scan_files':secrets['scanned_files'],'before_after_current':True,
  'distribution_channel':'source-candidate' if source_candidate else 'release',
  'publishable_release':not source_candidate,
  'native_builds':{
   'status':'not-built' if source_candidate else 'coordinated-release-required',
   'cargo_lockfiles':cargo_locks,'cargo_lockfiles_expected':cargo_expected,
   'reason':'Rust/Cargo indisponível neste host; nenhum binário nativo foi construído.' if source_candidate else None,
  },
 }

def import_external_evidence(destination:Path)->dict:
 configured=os.environ.get('PIGE360_EVIDENCE_DIR')
 if destination.is_symlink():raise RuntimeError(f'destino de evidência não pode ser link: {destination}')
 if not configured:
  if destination.exists():shutil.rmtree(destination)
  return {'status':'not_requested','files':0,'bytes':0}
 source=Path(configured).expanduser().resolve()
 if not source.is_dir():raise RuntimeError(f'PIGE360_EVIDENCE_DIR não é diretório: {source}')
 target_root=destination.resolve()
 if source==target_root or target_root.is_relative_to(source) or source.is_relative_to(target_root):raise RuntimeError('origem e destino de evidência externa não podem se sobrepor')
 files=[];total=0
 for path in sorted(source.rglob('*')):
  relative=path.relative_to(source)
  if path.is_symlink():raise RuntimeError(f'link simbólico recusado na evidência externa: {relative}')
  if not path.is_file():continue
  if any(part.startswith('.') for part in relative.parts) or path.name in EXCLUDED_NAMES or path.suffix.lower() not in EXTERNAL_EVIDENCE_SUFFIXES:
   raise RuntimeError(f'arquivo fora da allowlist de evidência externa: {relative}')
  size=path.stat().st_size
  if size>EXTERNAL_EVIDENCE_MAX_FILE_BYTES:raise RuntimeError(f'evidência externa excede 25 MiB: {relative}')
  total+=size
  if total>EXTERNAL_EVIDENCE_MAX_TOTAL_BYTES:raise RuntimeError('evidência externa excede 100 MiB')
  files.append((relative,path))
 if not files:raise RuntimeError('PIGE360_EVIDENCE_DIR não contém arquivos permitidos')
 with tempfile.TemporaryDirectory(prefix='pige360-external-evidence-scan-') as td:
  report=Path(td)/'secret-scan.json'
  process=subprocess.run([sys.executable,str(ROOT/'scripts/validation/secret_scan.py'),'--root',str(source),'--project-version',VERSION,'--strict','--output',str(report)],check=False,capture_output=True,text=True)
  if process.returncode!=0:raise RuntimeError(f'evidência externa reprovada pela varredura de segredos:\n{process.stdout[-2000:]}\n{process.stderr[-2000:]}')
  scan=read_object(report)
 if destination.exists():shutil.rmtree(destination)
 destination.mkdir(parents=True)
 for relative,path in files:
  target=destination/relative;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(path,target)
 return {'status':'passed','files':len(files),'bytes':total,'secret_scan_files':scan.get('scanned_files')}
def select_entries(prefixes:list[str],extras:list[str]|None=None):
 result=[]
 accepted=prefixes+(extras or [])
 for arc,p in source_entries(include_release_generated=True):
  if any(arc==x or arc.startswith(x.rstrip('/')+'/') for x in accepted):result.append((arc,p))
 return result
def source_timestamp(path:Path)->tuple[int,int,int,int,int,int]:
 value=time.gmtime(path.stat().st_mtime)[:6]
 if value[0]<1980:return (1980,1,1,0,0,0)
 if value[0]>2107:return (2107,12,31,23,59,58)
 return value
def make_zip(path:Path,entries:list[tuple[str,Path]],external:list[tuple[str,Path]]|None=None)->dict:
 path.parent.mkdir(parents=True,exist_ok=True);seen=set()
 # Monte o arquivo em um diretório privado irmão e publique-o por troca
 # atômica. Alguns filesystems deixam um artefato de copy-up no pathname de
 # staging depois do replace; mantê-lo fora da entrega permite removê-lo sem
 # tocar no pacote publicado. A cópia em fluxo evita carregar ZIPs externos
 # inteiros na memória ao incorporá-los ao bundle principal.
 staging=Path(tempfile.mkdtemp(dir=path.parent.parent,prefix=f'.{path.parent.name}.{path.name}.staging-'))
 temporary=staging/f'{path.name}.partial'
 try:
  with zipfile.ZipFile(temporary,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=9,strict_timestamps=True) as z:
   for arc,src in sorted(entries+(external or []),key=lambda x:x[0]):
    arc=arc.replace('\\','/').lstrip('/')
    if not arc or '..' in PurePosixPath(arc).parts or arc in seen:raise RuntimeError(f'caminho de archive inválido/duplicado: {arc}')
    if src.is_symlink():raise RuntimeError(f'link simbólico não permitido no pacote: {src}')
    source_stat=src.stat();seen.add(arc);info=zipfile.ZipInfo(arc,source_timestamp(src))
    permissions=0o755 if source_stat.st_mode & stat.S_IXUSR else 0o644
    info.external_attr=(stat.S_IFREG|permissions)<<16;info.compress_type=zipfile.ZIP_DEFLATED;info.create_system=3;info.file_size=source_stat.st_size
    with src.open('rb') as source_stream,z.open(info,'w') as archive_stream:
     shutil.copyfileobj(source_stream,archive_stream,length=1024*1024)
  with temporary.open('rb') as stream:os.fsync(stream.fileno())
  with zipfile.ZipFile(temporary) as z:
   if z.testzip() is not None:raise RuntimeError(f'ZIP corrompido: {path}')
  os.replace(temporary,path)
 finally:
  shutil.rmtree(staging,ignore_errors=False)
 return {'name':path.name,'path':str(path),'sha256':sha(path),'bytes':path.stat().st_size,'files':len(seen),'timestamp_policy':'source_mtime_utc'}

def assert_zip_snapshot(path:Path,expected:dict,*,stage:str)->dict:
 try:
  with zipfile.ZipFile(path) as archive:bad=archive.testzip()
 except (OSError,zipfile.BadZipFile) as exc:
  raise RuntimeError(f'ZIP imutável ficou ilegível em {stage}: {path}: {exc}') from exc
 current={'sha256':sha(path),'bytes':path.stat().st_size,'testzip':bad}
 if bad is not None or current['sha256']!=expected.get('sha256') or current['bytes']!=expected.get('bytes'):
  raise RuntimeError(f'ZIP imutável mudou em {stage}: {path.name}: esperado={expected}, atual={current}')
 return current
def tree_manifest(entries):
 files=[{'path':arc,'sha256':sha(p),'bytes':p.stat().st_size,'mtime_utc':datetime.fromtimestamp(p.stat().st_mtime,timezone.utc).isoformat()} for arc,p in entries]
 digest=hashlib.sha256(''.join(f"{x['sha256']}  {x['path']}\n" for x in files).encode()).hexdigest()
 data={'schema_version':2,'version':VERSION,'timestamp_policy':'source_mtime_utc','files_count':len(files),'tree_sha256':digest,'files':files}
 (ROOT/'release/source-tree-manifest.json').write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
 (ROOT/'release/final-tree.txt').write_text('\n'.join(x['path'] for x in files)+'\n',encoding='utf-8')
 return data
def validate_archives(packages:list[dict])->dict:
 errors=[];details=[]
 for pkg in packages:
  path=Path(pkg['path'])
  with zipfile.ZipFile(path) as z:
   names=z.namelist();bad=[n for n in names if n.startswith('/') or '..' in PurePosixPath(n).parts];forbidden=[n for n in names if any(part in EXCLUDED_PARTS for part in PurePosixPath(n).parts) or PurePosixPath(n).suffix.lower() in EXCLUDED_SUFFIX or PurePosixPath(n).name in EXCLUDED_NAMES or (PurePosixPath(n).name.startswith('.env.') and PurePosixPath(n).name!='.env.example')]
   if bad:errors.append({'archive':path.name,'path_traversal':bad[:10]})
   if forbidden:errors.append({'archive':path.name,'forbidden':forbidden[:20]})
   details.append({'archive':path.name,'files':len(names),'testzip':z.testzip(),'path_traversal':len(bad),'forbidden':len(forbidden)})
 return {'status':'passed' if not errors else 'failed','archives':details,'errors':errors}
def validate_source_preservation(path:Path,entries:list[tuple[str,Path]])->dict:
 expected={arc for arc,_ in entries}
 expected_vue_js=sorted(n for n in expected if n.endswith('.vue.js'))
 expected_main_js=sorted(n for n in expected if n.startswith('apps/') and n.endswith('/src/main.js'))
 with zipfile.ZipFile(path) as z:actual=set(z.namelist())
 missing=sorted(expected-actual)
 report={
  'status':'passed' if not missing else 'failed',
  'expected_source_files':len(expected),
  'vue_js_expected':len(expected_vue_js),'vue_js_preserved':len(set(expected_vue_js)&actual),
  'main_js_expected':len(expected_main_js),'main_js_preserved':len(set(expected_main_js)&actual),
  'missing':missing[:100],
 }
 if missing:raise RuntimeError(f'fontes omitidas do ZIP: {report}')
 return report
def validate_source_manifest(path:Path,tree:dict,current_entries:list[tuple[str,Path]]|None=None)->dict:
 expected={item['path']:item['sha256'] for item in tree.get('files',[]) if isinstance(item,dict) and item.get('path') and item.get('sha256')}
 with zipfile.ZipFile(path) as archive:
  actual_names=archive.namelist();actual=set(actual_names)
  missing=sorted(set(expected)-actual);unexpected=sorted(actual-set(expected));mismatches=[]
  for name in sorted(set(expected)&actual):
   digest=hashlib.sha256()
   with archive.open(name) as stream:
    for chunk in iter(lambda:stream.read(1024*1024),b''):digest.update(chunk)
   if digest.hexdigest()!=expected[name]:mismatches.append(name)
 current_entries=source_entries() if current_entries is None else current_entries;current={arc:sha(p) for arc,p in current_entries}
 current_missing=sorted(set(expected)-set(current));current_unexpected=sorted(set(current)-set(expected));current_mismatches=sorted(name for name in set(expected)&set(current) if expected[name]!=current[name])
 errors={'archive_missing':missing[:100],'archive_unexpected':unexpected[:100],'archive_hash_mismatches':mismatches[:100],'current_missing':current_missing[:100],'current_unexpected':current_unexpected[:100],'current_hash_mismatches':current_mismatches[:100]}
 status='passed' if not any(errors.values()) and len(expected)==tree.get('files_count') else 'failed'
 report={'status':status,'manifest_files':len(expected),'archive_files':len(actual_names),'tree_sha256':tree.get('tree_sha256'),**errors}
 if status!='passed':raise RuntimeError(f'ZIP fonte diverge do manifesto imutável: {report}')
 return report
def public_package(package:dict)->dict:
 return {key:value for key,value in package.items() if key!='path'}
def distribution_stem(source_candidate:bool)->str:
 return f'PIGE360-{VERSION}-source-candidate' if source_candidate else f'PIGE360-{VERSION}'
def annotate_source_candidate(path:Path,evidence_gate:dict)->None:
 data=read_object(path)
 data['distribution']={
  'channel':'source-candidate','status':'partial','publishable_release':False,
  'scope':'fonte, self-hosted e kit CI/CD para instalação e homologação',
  'native_builds':evidence_gate['native_builds'],
 }
 path.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def write_checksums(delivery:Path)->None:
 candidates=[p for p in sorted(delivery.iterdir()) if p.name not in {'SHA256SUMS',DELIVERY_MARKER}]
 invalid=[p.name for p in candidates if not p.is_file() or p.is_symlink() or p.name.startswith('.') or p.suffix=='.tmp']
 if invalid:raise RuntimeError(f'diretório de entrega contém resíduos ou entradas inválidas: {invalid}')
 lines=[f'{sha(p)}  {p.name}' for p in candidates]
 (delivery/'SHA256SUMS').write_text('\n'.join(lines)+'\n',encoding='utf-8')
 for line in lines:
  expected,name=line.split('  ',1)
  if sha(delivery/name)!=expected:raise RuntimeError(f'checksum divergente: {name}')
def build_self_hosted_only(delivery:Path)->None:
 entries=select_entries(SELF_HOSTED_PREFIXES)
 path=delivery/f'PIGE360-{VERSION}-self-hosted.zip';package=make_zip(path,entries)
 with tempfile.TemporaryDirectory(prefix='pige360-selfhost-repro-') as td:
  second=Path(td)/path.name;make_zip(second,entries);reproducible=sha(second)==package['sha256']
 if not reproducible:raise RuntimeError('ZIP self-hosted não reproduzível')
 validation=validate_archives([package]);validation.update({'self_hosted_reproducible':True,'timestamp_policy':'source_mtime_utc','generated_at':datetime.now(timezone.utc).isoformat()})
 if validation['status']!='passed':raise RuntimeError(validation)
 (delivery/'archive-validation-report.json').write_text(json.dumps(validation,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 summary={'status':'passed','mode':'self-hosted-only','version':VERSION,'output_dir':'.','packages':[public_package(package)],'self_hosted_reproducible':True,'timestamp_policy':'source_mtime_utc'}
 (delivery/'DELIVERY-SUMMARY.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');write_checksums(delivery)
 print(json.dumps({'status':'passed','mode':'self-hosted-only','output':str(delivery),'packages':[{k:package[k] for k in ['name','sha256','bytes','files']}],'self_hosted_reproducible':True,'files':len(list(delivery.iterdir()))},ensure_ascii=False))
def main():
 parser=argparse.ArgumentParser();parser.add_argument('--output-dir',default=str(DELIVERY));mode=parser.add_mutually_exclusive_group();mode.add_argument('--self-hosted-only',action='store_true',help='Gera somente o ZIP self-hosted sem depender das evidências completas da release');mode.add_argument('--source-candidate',action='store_true',help='Gera candidato parcial de fonte/instalação; nunca representa release nem binários nativos');a=parser.parse_args()
 # O descritor permanece aberto até o retorno de main. O lock do SO evita que
 # duas invocações recriem ou truncem os mesmos caminhos de entrega.
 _delivery_lock=acquire_delivery_lock(Path(a.output_dir))
 if a.self_hosted_only:
  delivery=prepare_delivery(Path(a.output_dir))
  build_self_hosted_only(delivery)
  return
 final_secret_scan()
 evidence_gate=validate_release_evidence(source_candidate=a.source_candidate)
 delivery=prepare_delivery(Path(a.output_dir))
 stem=distribution_stem(a.source_candidate)
 # O relatório é um asset obrigatório do bundle. Gere-o depois das evidências
 # do CI e antes de calcular os manifests/ZIPs, para evitar pacote incompleto.
 subprocess.run([sys.executable,str(ROOT/'scripts/release/generate_evidence_pdf.py')],check=True)
 evidence_pdf=ROOT/f'release/artifacts/reports/PIGE360-{VERSION}-relatorio-evidencias.pdf'
 if not evidence_pdf.is_file():raise RuntimeError(f'relatório de evidências ausente: {evidence_pdf}')
 # Evidência externa nunca é importada implicitamente do workspace pai. Quando
 # solicitada, exige PIGE360_EVIDENCE_DIR, allowlist textual e secret scan.
 external_evidence=import_external_evidence(ROOT/'release/evidence')
 entries=source_entries();tree=tree_manifest(entries)
 # Source provenance is stable for the package build.
 subprocess.run([sys.executable,str(ROOT/'scripts/release/generate_provenance.py')],check=True,stdout=subprocess.DEVNULL)
 source_path=delivery/f'{stem}-source.zip';source=make_zip(source_path,entries)
 source_preservation=validate_source_preservation(source_path,entries)
 source_manifest_validation=validate_source_manifest(source_path,tree)
 # Reproducibility check: build from identical inputs a second time.
 with tempfile.TemporaryDirectory(prefix='pige360-repro-') as td:
  second=Path(td)/source_path.name;make_zip(second,entries);repro=sha(second)==source['sha256']
 if not repro:raise RuntimeError('ZIP source não reproduzível')
 selfhost_path=delivery/f'{stem}-self-hosted.zip';selfhost=make_zip(selfhost_path,select_entries(SELF_HOSTED_PREFIXES))
 wf_prefix=['.github/workflows','CI_CD_KIT_LOCAL','scripts/ci','scripts/deploy','scripts/release','scripts/desktop','scripts/mobile','scripts/oci','scripts/supply-chain','scripts/validation','docs/ci-cd','deployments','compose.yaml','compose.production.yaml','VERSION']
 workflows_path=delivery/f'{stem}-workflows-ci-cd.zip';workflows=make_zip(workflows_path,select_entries(wf_prefix))
 prelim=[source,selfhost,workflows];prelim_public=[public_package(package) for package in prelim]
 packages_json=ROOT/'release/packages-preliminary.json';packages_json.write_text(json.dumps(prelim_public,ensure_ascii=False,indent=2),encoding='utf-8')
 prepackage=ROOT/'release'/(f'{stem}-manifest-prepackage.json' if a.source_candidate else f'{stem}-release-manifest-prepackage.json')
 subprocess.run([sys.executable,str(ROOT/'scripts/release/generate-manifest.py'),'--packages-json',str(packages_json),'--output',str(prepackage)],check=True,stdout=subprocess.DEVNULL)
 if a.source_candidate:annotate_source_candidate(prepackage,evidence_gate)
 release_prefix=['VERSION','README.md','CHANGELOG.md','SECURITY.md','LICENSE-NOTICE.md','.env.example','docs','deployments','release/artifacts','release/reports','release/evidence','release/toolchain-inventory.json','release/project-validation.json','release/secret-scan-report.json','release/source-tree-manifest.json','release/final-tree.txt','release/PIGE360-'+VERSION+'-sbom.cdx.json','release/PIGE360-'+VERSION+'-source-provenance.intoto.json',prepackage.relative_to(ROOT).as_posix(),'docs/api','packages/api-sdk','CI_CD_KIT_LOCAL','.github/workflows','compose.yaml','compose.production.yaml']
 release_path=delivery/(f'{stem}-bundle.zip' if a.source_candidate else f'{stem}-release-bundle.zip')
 assert_zip_snapshot(source_path,source,stage='antes do bundle')
 assert_zip_snapshot(selfhost_path,selfhost,stage='antes do bundle')
 assert_zip_snapshot(workflows_path,workflows,stage='antes do bundle')
 release_bundle=make_zip(release_path,select_entries(release_prefix),[(f'packages/{source_path.name}',source_path),(f'packages/{selfhost_path.name}',selfhost_path),(f'packages/{workflows_path.name}',workflows_path)])
 assert_zip_snapshot(source_path,source,stage='depois do bundle')
 assert_zip_snapshot(selfhost_path,selfhost,stage='depois do bundle')
 assert_zip_snapshot(workflows_path,workflows,stage='depois do bundle')
 packages=[source,release_bundle,selfhost,workflows]
 package_subjects=[{'name':p['name'],'digest':{'sha256':p['sha256']}} for p in packages]
 subjects_file=ROOT/'release/package-subjects.json';subjects_file.write_text(json.dumps(package_subjects,ensure_ascii=False,indent=2),encoding='utf-8')
 final_manifest=delivery/(f'{stem}-manifest.json' if a.source_candidate else f'{stem}-release-manifest.json')
 # Generate final manifest directly after writing package metadata.
 packages_public=[public_package(package) for package in packages]
 (ROOT/'release/packages-final.json').write_text(json.dumps(packages_public,ensure_ascii=False,indent=2),encoding='utf-8')
 subprocess.run([sys.executable,str(ROOT/'scripts/release/generate-manifest.py'),'--packages-json',str(ROOT/'release/packages-final.json'),'--output',str(final_manifest)],check=True,capture_output=True,text=True)
 if a.source_candidate:annotate_source_candidate(final_manifest,evidence_gate)
 provenance=delivery/(f'{stem}-provenance.intoto.json' if a.source_candidate else f'{stem}-release-provenance.intoto.json')
 subprocess.run([sys.executable,str(ROOT/'scripts/release/generate_provenance.py'),'--subjects-json',str(subjects_file),'--output',str(provenance)],check=True,capture_output=True,text=True)
 if a.source_candidate:annotate_source_candidate(provenance,evidence_gate)
 # Expose key evidence beside the ZIPs.
 copies=[ROOT/f'release/PIGE360-{VERSION}-sbom.cdx.json',ROOT/f'release/artifacts/oci/PIGE360-{VERSION}-images-oci.tar',ROOT/f'release/artifacts/oci/PIGE360-{VERSION}-images-digests.json',ROOT/f'release/artifacts/reports/PIGE360-{VERSION}-relatorio-evidencias.pdf',ROOT/'release/reports/test-report.json',ROOT/'release/reports/build-report.json',ROOT/'release/reports/local-ci-report.json',ROOT/'release/project-validation.json',ROOT/'docs/design/visual-regression-report.json']
 for src in copies:shutil.copy2(src,delivery/src.name)
 # Reconfere a árvore depois de todos os geradores: nenhuma alteração concorrente
 # pode ocorrer entre o manifesto, o ZIP e a conclusão da entrega.
 assert_zip_snapshot(source_path,source,stage='validação final')
 assert_zip_snapshot(selfhost_path,selfhost,stage='validação final')
 assert_zip_snapshot(workflows_path,workflows,stage='validação final')
 assert_zip_snapshot(release_path,release_bundle,stage='validação final')
 source_manifest_validation=validate_source_manifest(source_path,tree)
 validation=validate_archives(packages);validation['distribution_status']='partial' if a.source_candidate else 'release-artifacts-validated';validation['publishable_release']=not a.source_candidate;validation['source_reproducible']=repro;validation['source_preservation']=source_preservation;validation['source_manifest_validation']=source_manifest_validation;validation['evidence_gate']=evidence_gate;validation['external_evidence']=external_evidence;validation['timestamp_policy']='source_mtime_utc';validation['generated_at']=datetime.now(timezone.utc).isoformat();validation_path=delivery/'archive-validation-report.json';validation_path.write_text(json.dumps(validation,ensure_ascii=False,indent=2),encoding='utf-8')
 if validation['status']!='passed':raise RuntimeError(validation)
 # Delivery checksums (excluding the checksum file itself).
 write_checksums(delivery)
 summary={'status':'partial' if a.source_candidate else 'passed','distribution_channel':'source-candidate' if a.source_candidate else 'release','publishable_release':not a.source_candidate,'native_builds':evidence_gate['native_builds'],'version':VERSION,'output_dir':'.','packages':packages_public,'source_reproducible':repro,'source_preservation':source_preservation,'source_manifest_validation':source_manifest_validation,'evidence_gate':evidence_gate,'external_evidence':external_evidence,'timestamp_policy':'source_mtime_utc','archive_validation':validation,'sha256s':'SHA256SUMS'}
 (delivery/'DELIVERY-SUMMARY.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
 # Include summary in checksums by regenerating once.
 write_checksums(delivery)
 print(json.dumps({'status':'partial' if a.source_candidate else 'passed','distribution_channel':'source-candidate' if a.source_candidate else 'release','publishable_release':not a.source_candidate,'native_builds':evidence_gate['native_builds'],'output':str(delivery),'packages':[{k:p[k] for k in ['name','sha256','bytes','files']} for p in packages],'source_reproducible':repro,'source_preservation':source_preservation,'files':len(list(delivery.iterdir()))},ensure_ascii=False))
if __name__=='__main__':main()
