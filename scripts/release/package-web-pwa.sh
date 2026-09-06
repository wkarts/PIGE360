#!/usr/bin/env bash
set -euo pipefail

version="$(tr -d '[:space:]' < VERSION)"
prerelease_id='(0|[1-9][0-9]*|[0-9A-Za-z-]*[A-Za-z-][0-9A-Za-z-]*)'
semver_re="^(0|[1-9][0-9]*)\\.(0|[1-9][0-9]*)\\.(0|[1-9][0-9]*)(-${prerelease_id}(\\.${prerelease_id})*)?(\\+[0-9A-Za-z-]+(\\.[0-9A-Za-z-]+)*)?$"
[[ "$version" =~ $semver_re ]] || {
  echo "VERSION SemVer inválida: $version" >&2
  exit 2
}

# Gate leve para testar versões stable/prerelease sem recompilar os 13 PWAs.
if [[ "${1:-}" == '--validate-version-only' ]]; then
  exit 0
fi
if (( $# > 0 )); then
  echo "Uso: $0 [--validate-version-only]" >&2
  exit 2
fi

bash scripts/frontend/install-dependencies.sh
npm run --silent validate:ts
npm run --silent build:web
python3 scripts/validation/validate_pwa_builds.py
command -v unzip >/dev/null 2>&1 || {
  echo 'unzip é obrigatório para validar os pacotes PWA.' >&2
  exit 3
}

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
  [[ -s "$archive" ]] || { echo "PWA vazia: $archive" >&2; exit 4; }
  unzip -tq "$archive" >/dev/null
  ((count += 1))
done < <(find apps -mindepth 2 -maxdepth 2 -type d -name dist -print0 | sort -z)

((count == 13)) || {
  echo "Esperados 13 PWAs; encontrados $count." >&2
  exit 4
}

(
  cd "$output_dir"
  sha256sum ./*.zip > "PIGE360-${version}-web-pwa-SHA256SUMS"
  sha256sum --check "PIGE360-${version}-web-pwa-SHA256SUMS"
)
