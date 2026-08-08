#!/usr/bin/env python3
from pathlib import Path
import json, sys
ROOT=Path(__file__).resolve().parents[1]
required=[
 'scripts/frontend/install-dependencies.sh','scripts/desktop/build-all.sh','scripts/mobile/build-android.sh',
 'scripts/mobile/build-ios.sh','scripts/mobile/sign-android.sh','scripts/mobile/sign-ios.sh','scripts/mobile/build-tenant-app.sh',
 'scripts/release/package-local.sh','scripts/ci/run-all.sh'
]
missing=[x for x in required if not (ROOT/x).is_file()]
for rel in required:
 p=ROOT/rel
 if p.is_file() and p.suffix in {'.sh',''} and not (p.stat().st_mode & 0o111): missing.append(rel+':not-executable')
print(json.dumps({'status':'passed' if not missing else 'failed','mode':'validate-only','missing':missing},ensure_ascii=False))
raise SystemExit(1 if missing else 0)
