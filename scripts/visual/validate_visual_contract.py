#!/usr/bin/env python3
from __future__ import annotations
import hashlib
import json
from pathlib import Path
from PIL import Image

ROOT=Path(__file__).resolve().parents[2]
MANIFEST=ROOT/'packages/visual-testing/baselines/visual-baseline-manifest.json'
SCREENS=ROOT/'docs/design/screen-catalog/screens'
forbidden=("PIGE360","ARGWS","WWSoftwares","Projeto Escola 360")
errors=[]
if not MANIFEST.is_file():errors.append('Manifesto visual ausente.')
else:
    data=json.loads(MANIFEST.read_text(encoding='utf-8'))
    records=data.get('records',[])
    if len({r['screen'] for r in records}) != 40: errors.append('As 40 superfícies canônicas não foram renderizadas.')
    if len(records) < 100: errors.append(f'Quantidade insuficiente de variantes: {len(records)}.')
    for item in records:
        path=ROOT/item['path']
        if not path.is_file():errors.append(f'Screenshot ausente: {item["path"]}');continue
        digest=hashlib.sha256(path.read_bytes()).hexdigest()
        if digest != item['sha256']:errors.append(f'Hash divergente: {item["path"]}')
        with Image.open(path) as im:
            expected=(item['viewport']['width'],item['viewport']['height'])
            if im.size != expected:errors.append(f'Dimensão divergente {item["path"]}: {im.size} != {expected}')
for html_path in sorted(SCREENS.glob('*.html')):
    text=html_path.read_text(encoding='utf-8')
    if 'data-context="tenant"' in text:
        for term in forbidden:
            if term in text:errors.append(f'Vazamento de marca global em {html_path.name}: {term}')
    if 'aria-label=' not in text: errors.append(f'Acessibilidade básica ausente em {html_path.name}')
if errors:
    print(json.dumps({'status':'failed','errors':errors},ensure_ascii=False,indent=2));raise SystemExit(1)
print(json.dumps({'status':'passed','screens':40,'screenshots':len(json.loads(MANIFEST.read_text())['records']),'tenant_brand_leakage':False},ensure_ascii=False))
