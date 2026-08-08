#!/bin/sh
set -eu
target="${1:-}"
[ -n "$target" ] || { echo 'Informe o target Rust.' >&2; exit 2; }
command -v cargo >/dev/null || { echo 'SKIPPED_NOT_CONFIGURED: cargo não disponível.' >&2; exit 3; }
command -v npm >/dev/null || { echo 'SKIPPED_NOT_CONFIGURED: npm não disponível.' >&2; exit 3; }
bash scripts/frontend/install-dependencies.sh
mkdir -p release/artifacts/desktop
for app in desktop-admin pos-app; do
  (cd "apps/$app" && npx --no-install tauri build --target "$target")
done
find apps -path '*/src-tauri/target/*/release/bundle/*' -type f -exec cp {} release/artifacts/desktop/ \;
