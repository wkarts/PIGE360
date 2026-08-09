#!/bin/sh
set -eu
target="${1:-}"
[ -n "$target" ] || { echo 'Informe o target Rust.' >&2; exit 2; }
command -v cargo >/dev/null 2>&1 || { echo 'cargo não disponível.' >&2; exit 3; }
command -v npm >/dev/null 2>&1 || { echo 'npm não disponível.' >&2; exit 3; }

bash scripts/frontend/install-dependencies.sh
mkdir -p release/artifacts/desktop

for app in desktop-admin pos-app; do
  echo "Compilando $app para $target"
  (cd "apps/$app" && npx --no-install tauri build --target "$target")
  found=0
  while IFS= read -r file; do
    [ -n "$file" ] || continue
    found=1
    cp "$file" "release/artifacts/desktop/${app}-${target}-$(basename "$file")"
  done <<EOF
$(find "apps/$app/src-tauri/target/$target/release/bundle" -type f 2>/dev/null | sort)
EOF
  [ "$found" -eq 1 ] || { echo "Nenhum bundle desktop gerado para $app / $target" >&2; exit 5; }
done

find release/artifacts/desktop -maxdepth 1 -type f -print | sort
