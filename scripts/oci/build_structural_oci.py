#!/usr/bin/env python3
"""Gera um OCI Image Layout estrutural e autocontido.

Este gerador não substitui `docker build`. Ele existe para transportar, por digest,
os descritores e fontes de imagem quando o runtime OCI não está disponível. Todos
os manifests recebem labels que impedem confusão com imagem executável validada.
"""
from __future__ import annotations

import hashlib
import io
import json
import shutil
import tarfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT=Path(__file__).resolve().parents[2]
VERSION=(ROOT/'VERSION').read_text().strip()
OUT=ROOT/'release/artifacts/oci'
LAYOUT=OUT/'layout'
FIXED_TIME=0
CREATED='2026-08-07T00:00:00Z'
IMAGES={
 'pige360-base-python':'infra/docker/base/Dockerfile.python',
 'pige360-base-node':'infra/docker/base/Dockerfile.node',
 'pige360-base-rust-tauri':'infra/docker/base/Dockerfile.rust-tauri',
 'pige360-base-runtime':'infra/docker/base/Dockerfile.runtime',
 'pige360':'compose.yaml',
 'pige360-api':'infra/docker/Dockerfile.api',
 'pige360-web':'infra/docker/Dockerfile.web',
 'pige360-worker':'infra/docker/Dockerfile.worker',
 'pige360-platform-console':'infra/docker/Dockerfile.web',
 'pige360-app-factory':'infra/docker/Dockerfile.api',
 'pige360-migrations':'infra/docker/Dockerfile.migrations',
 'pige360-reporting':'infra/docker/Dockerfile.reporting',
}

def digest(data:bytes)->str:return hashlib.sha256(data).hexdigest()
def canonical(value:Any)->bytes:return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()
def blob(data:bytes)->tuple[str,int]:
 d=digest(data);p=LAYOUT/'blobs/sha256'/d;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(data);return d,len(data)
def layer_bytes(name:str,source:Path)->bytes:
 buf=io.BytesIO()
 with tarfile.open(fileobj=buf,mode='w',format=tarfile.PAX_FORMAT) as tar:
  notice=(f'PIGE360 {VERSION}\nArtefato OCI estrutural local para {name}.\n'
          'RUNTIME_EXECUTABLE=false\nVALIDATION=structural-only\n'
          'Construa a imagem executável com o Dockerfile incluído em runner OCI autorizado.\n').encode()
  entries=[('usr/share/pige360/IMAGE-NOTICE.txt',notice),('usr/share/pige360/source/'+source.name,source.read_bytes())]
  for path,data in entries:
   info=tarfile.TarInfo(path);info.size=len(data);info.mtime=FIXED_TIME;info.uid=info.gid=0;info.uname=info.gname='root';info.mode=0o644;tar.addfile(info,io.BytesIO(data))
 return buf.getvalue()
def main()->None:
 if OUT.exists():shutil.rmtree(OUT)
 (LAYOUT/'blobs/sha256').mkdir(parents=True)
 (LAYOUT/'oci-layout').write_text('{"imageLayoutVersion":"1.0.0"}\n',encoding='utf-8')
 descriptors=[];records=[]
 for name,source_rel in IMAGES.items():
  source=ROOT/source_rel;layer=layer_bytes(name,source);ld,ls=blob(layer)
  config={
   'created':CREATED,'architecture':'amd64','os':'linux',
   'config':{'User':'10001:10001','Env':['REMOTE_REGISTRY_ENABLED=false','REMOTE_RELEASE_ENABLED=false','REMOTE_DEPLOY_ENABLED=false'],
             'Labels':{'org.opencontainers.image.title':name,'org.opencontainers.image.version':VERSION,'org.opencontainers.image.source':'local-workspace','org.pige360.validation':'structural-only','org.pige360.runtime-executable':'false'}},
   'rootfs':{'type':'layers','diff_ids':['sha256:'+ld]},'history':[{'created':CREATED,'created_by':'pige360 structural OCI generator','comment':'not runtime built'}]
  }
  cb=canonical(config);cd,cs=blob(cb)
  manifest={'schemaVersion':2,'mediaType':'application/vnd.oci.image.manifest.v1+json','config':{'mediaType':'application/vnd.oci.image.config.v1+json','digest':'sha256:'+cd,'size':cs},'layers':[{'mediaType':'application/vnd.oci.image.layer.v1.tar','digest':'sha256:'+ld,'size':ls,'annotations':{'org.opencontainers.image.title':source_rel}}], 'annotations':{'org.opencontainers.image.ref.name':f'{name}:{VERSION}','org.pige360.validation':'structural-only'}}
  mb=canonical(manifest);md,ms=blob(mb)
  descriptor={'mediaType':'application/vnd.oci.image.manifest.v1+json','digest':'sha256:'+md,'size':ms,'annotations':{'org.opencontainers.image.ref.name':f'{name}:{VERSION}','org.opencontainers.image.title':name,'org.pige360.validation':'structural-only'}}
  descriptors.append(descriptor)
  records.append({'name':name,'tag':VERSION,'manifest_digest':'sha256:'+md,'config_digest':'sha256:'+cd,'layer_digest':'sha256:'+ld,'source':source_rel,'validation':'oci-layout-structural-only','runtime_executable':False})
 index={'schemaVersion':2,'mediaType':'application/vnd.oci.image.index.v1+json','manifests':descriptors,'annotations':{'org.opencontainers.image.title':'PIGE360 local structural OCI bundle','org.opencontainers.image.version':VERSION,'org.pige360.runtime-validation':'not-executed'}}
 (LAYOUT/'index.json').write_bytes(canonical(index))
 # deterministic tar of layout
 tar_path=OUT/f'PIGE360-{VERSION}-images-oci.tar'
 with tarfile.open(tar_path,'w',format=tarfile.PAX_FORMAT) as tar:
  for p in sorted(LAYOUT.rglob('*')):
   if not p.is_file():continue
   info=tar.gettarinfo(str(p),arcname=p.relative_to(LAYOUT).as_posix());info.mtime=FIXED_TIME;info.uid=info.gid=0;info.uname=info.gname='root'
   with p.open('rb') as f:tar.addfile(info,f)
 digests={'schema_version':1,'version':VERSION,'generated_at':datetime.now(timezone.utc).isoformat(),'runtime_engine_available':False,'runtime_build_executed':False,'bundle':{'path':tar_path.relative_to(ROOT).as_posix(),'sha256':digest(tar_path.read_bytes()),'bytes':tar_path.stat().st_size},'images':records}
 (OUT/f'PIGE360-{VERSION}-images-digests.json').write_text(json.dumps(digests,ensure_ascii=False,indent=2),encoding='utf-8')
 # verify all referenced blobs and archive
 for desc in index['manifests']:
  d=desc['digest'].split(':',1)[1];p=LAYOUT/'blobs/sha256'/d;assert p.is_file() and digest(p.read_bytes())==d and p.stat().st_size==desc['size']
 with tarfile.open(tar_path) as tar:assert {'oci-layout','index.json'} <= set(tar.getnames())
 print(json.dumps({'status':'passed','images':len(records),'bundle':str(tar_path),'runtime_executable':False,'validation':'structural-only'},ensure_ascii=False))
if __name__=='__main__':main()
