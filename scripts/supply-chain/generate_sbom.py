#!/usr/bin/env python3
from __future__ import annotations
import argparse,hashlib,json,re,uuid
from datetime import datetime,timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];VERSION=(ROOT/'VERSION').read_text().strip()
def bomref(kind,name,version):return hashlib.sha256(f'{kind}:{name}:{version}'.encode()).hexdigest()[:32]
def component(kind,name,version,**extra):
 d={'type':kind,'bom-ref':bomref(kind,name,version),'name':name,'version':version};d.update(extra);return d
def main():
 p=argparse.ArgumentParser();p.add_argument('--check',action='store_true');p.add_argument('--output');a=p.parse_args();components=[]
 lock=ROOT/'backend/requirements.lock'
 for line in lock.read_text().splitlines():
  if '==' in line and not line.startswith('#'):
   name,ver=line.split('==',1);components.append(component('library',name,ver,purl=f'pkg:pypi/{name.lower()}@{ver}'))
 for pkg in sorted((ROOT/'apps').glob('*/package.json'))+sorted((ROOT/'packages').glob('*/package.json')):
  data=json.loads(pkg.read_text());name=data.get('name',pkg.parent.name);ver=data.get('version',VERSION);components.append(component('application' if pkg.parent.parent.name=='apps' else 'library',name,ver,properties=[{'name':'pige360:path','value':pkg.parent.relative_to(ROOT).as_posix()}]))
 cargo=ROOT/'rust/Cargo.toml'
 for cp in sorted((ROOT/'rust/crates').glob('*/Cargo.toml')):
  text=cp.read_text();m=re.search(r'^name\s*=\s*"([^"]+)"',text,re.M);components.append(component('library',m.group(1) if m else cp.parent.name,VERSION,purl=f'pkg:cargo/{m.group(1) if m else cp.parent.name}@{VERSION}'))
 for dockerfile in sorted((ROOT/'infra/docker').rglob('Dockerfile*')):
  for image in re.findall(r'^FROM\s+([^\s]+)',dockerfile.read_text(),re.M):
   if image.startswith('pige360-'):continue
   components.append(component('container',image.split(':')[0],image.split(':',1)[1] if ':' in image else 'unpinned',properties=[{'name':'pige360:declared-in','value':dockerfile.relative_to(ROOT).as_posix()}]))
 brand=ROOT/'packages/tenant-branding/brands/platform-pige360'
 hashes=[]
 for f in sorted(brand.rglob('*')):
  if f.is_file():hashes.append({'alg':'SHA-256','content':hashlib.sha256(f.read_bytes()).hexdigest()})
 components.append(component('data','pige360-official-branding',VERSION,hashes=hashes[:100],properties=[{'name':'pige360:asset-count','value':str(len(hashes))}]))
 # deduplicate by bom-ref
 unique={c['bom-ref']:c for c in components};components=list(unique.values())
 serial='urn:uuid:'+str(uuid.uuid5(uuid.NAMESPACE_URL,'pige360:'+VERSION+':local-sbom'))
 sbom={'bomFormat':'CycloneDX','specVersion':'1.6','serialNumber':serial,'version':1,'metadata':{'timestamp':datetime.now(timezone.utc).isoformat(),'tools':{'components':[{'type':'application','name':'pige360-local-sbom-generator','version':VERSION}]},'component':component('application','PIGE360',VERSION)},'components':components,'properties':[{'name':'pige360:network-used','value':'false'},{'name':'pige360:scope','value':'source-and-declared-runtime'}]}
 out=Path(a.output) if a.output else ROOT/f'release/PIGE360-{VERSION}-sbom.cdx.json';out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(sbom,ensure_ascii=False,indent=2),encoding='utf-8')
 errors=[]
 if sbom['bomFormat']!='CycloneDX' or sbom['specVersion']!='1.6' or not components:errors.append('estrutura SBOM inválida')
 print(json.dumps({'status':'passed' if not errors else 'failed','output':str(out),'components':len(components),'errors':errors},ensure_ascii=False));raise SystemExit(0 if not errors else 1)
if __name__=='__main__':main()
