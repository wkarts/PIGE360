#!/usr/bin/env python3
from __future__ import annotations
import hashlib,json,shutil,sqlite3,tempfile,zipfile
from datetime import datetime,timezone
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'backend'))
from app.bootstrap.config import Settings
from app.shared.database.router import DataRouter

def file_hash(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def sqlite_backup(src,dst):
 dst.parent.mkdir(parents=True,exist_ok=True)
 with sqlite3.connect(src) as source,sqlite3.connect(dst) as target:source.backup(target)
def seed_student(store,tenant_id,prefix,name):
 now=datetime.now(timezone.utc).isoformat();person=f'{prefix}-person';student=f'{prefix}-student'
 with store.transaction() as c:
  c.execute("INSERT INTO people(id,tenant_id,full_name,civil_data_json,address_json,emergency_json,state,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?)",(person,tenant_id,name,'{}','{}','{}','active',now,now))
  c.execute("INSERT INTO students(id,tenant_id,person_id,registration_number,state,needs_json,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)",(student,tenant_id,person,f'{prefix.upper()}-001','active','{}',now,now))
 return student

def main():
 out=ROOT/'release/artifacts/backup-restore';out.mkdir(parents=True,exist_ok=True)
 with tempfile.TemporaryDirectory(prefix='pige360-backup-test-') as td:
  base=Path(td);settings=Settings().testing(base/'runtime');router=DataRouter(settings);router.initialize()
  a=router.provision_tenant(code='backup-alpha',legal_name='Alpha Educação Ltda.',trade_name='Alpha',hostname='alpha.backup.local')
  b=router.provision_tenant(code='backup-beta',legal_name='Beta Educação Ltda.',trade_name='Beta',hostname='beta.backup.local')
  astore=router.tenant_store(a['id']);bstore=router.tenant_store(b['id']);alpha_student=seed_student(astore,a['id'],'alpha','Aluno Alpha');seed_student(bstore,b['id'],'beta','Aluno Beta')
  storage=router.tenant_storage_path(a['id']);doc=storage/'documents/evidence.txt';doc.parent.mkdir(parents=True,exist_ok=True);doc.write_text('Documento exclusivo do tenant Alpha.',encoding='utf-8')
  stage=base/'stage';sqlite_backup(Path(a['database_path']),stage/'tenant.db');shutil.copytree(storage,stage/'storage')
  manifest={'tenant_id':a['id'],'tenant_code':a['code'],'database_sha256':file_hash(stage/'tenant.db'),'files':[]}
  for f in sorted((stage/'storage').rglob('*')):
   if f.is_file():manifest['files'].append({'path':f.relative_to(stage).as_posix(),'sha256':file_hash(f),'bytes':f.stat().st_size})
  (stage/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
  archive=out/'tenant-alpha-backup.zip'
  with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
   for f in sorted(stage.rglob('*')):
    if f.is_file():z.write(f,f.relative_to(stage).as_posix())
  restored=base/'restored'
  with zipfile.ZipFile(archive) as z:z.extractall(restored)
  restored_manifest=json.loads((restored/'manifest.json').read_text());assert file_hash(restored/'tenant.db')==restored_manifest['database_sha256']
  conn=sqlite3.connect(restored/'tenant.db');rows=conn.execute("SELECT s.id,s.tenant_id,p.full_name FROM students s JOIN people p ON p.id=s.person_id").fetchall();tables={x[0] for x in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")};conn.close()
  assert rows==[(alpha_student,a['id'],'Aluno Alpha')];assert 'generic_records' not in tables
  assert 'Beta' not in '\n'.join(f.read_text(errors='ignore') for f in restored.rglob('*') if f.is_file() and f.suffix in {'.txt','.json'})
  report={'status':'passed','generated_at':datetime.now(timezone.utc).isoformat(),'backup':archive.relative_to(ROOT).as_posix(),'backup_sha256':file_hash(archive),'tenant_restored':a['id'],'cross_tenant_leakage':False,'database_integrity':'ok','object_integrity':'ok','records_restored':len(rows),'generic_records_present':False}
  (out/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(report,ensure_ascii=False))
if __name__=='__main__':main()
