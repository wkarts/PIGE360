#!/usr/bin/env bash
set -euo pipefail

version="$(tr -d '[:space:]' < VERSION)"
[[ "$version" =~ ^[0-9]+\.[0-9]+\.[0-9]+-alpha\.[0-9]+$ ]] || {
  echo "VERSION inválida para pré-lançamento: $version" >&2
  exit 2
}

bash scripts/frontend/install-dependencies.sh
npm run --silent validate:ts
npm run --silent build:web

output_dir="release/artifacts/web"
rm -rf "$output_dir"
mkdir -p "$output_dir"

count=0
while IFS= read -r -d '' dist; do
  app="$(basename "$(dirname "$dist")")"
  archive="$output_dir/PIGE360-${version}-${app}-pwa.zip"
  (
    cd "$dist"
    zip -qr "../../../$archive" .
  )
  ((count += 1))
done < <(find apps -mindepth 2 -maxdepth 2 -type d -name dist -print0 | sort -z)

((count == 13)) || {
  echo "Esperados 13 PWAs; encontrados $count." >&2
  exit 4
}

sha256sum "$output_dir"/*.zip > "$output_dir/PIGE360-${version}-web-pwa-SHA256SUMS"
