#!/bin/sh
set -eu

usage() {
  cat <<'EOF'
Uso: scripts/mobile/build-ios.sh [--mode <local-signing|store>]
EOF
}

mode='store'
while [ "$#" -gt 0 ]; do
  case "$1" in
    --mode) mode="${2:?Informe o modo após --mode}"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Argumento iOS desconhecido: $1" >&2; usage >&2; exit 2 ;;
  esac
done

case "$mode" in
  local-signing|store) ;;
  *) echo "Modo iOS inválido: $mode" >&2; exit 2 ;;
esac

command -v xcodebuild >/dev/null || { echo 'SKIPPED_NOT_CONFIGURED: Xcode ausente.' >&2; exit 3; }
command -v cargo >/dev/null || { echo 'SKIPPED_NOT_CONFIGURED: Rust ausente.' >&2; exit 3; }
command -v ditto >/dev/null || { echo 'SKIPPED_NOT_CONFIGURED: ditto ausente.' >&2; exit 3; }
command -v lipo >/dev/null || { echo 'SKIPPED_NOT_CONFIGURED: lipo ausente.' >&2; exit 3; }
command -v python3 >/dev/null || { echo 'SKIPPED_NOT_CONFIGURED: Python 3 ausente.' >&2; exit 3; }

if [ "$mode" = 'store' ] && [ -z "${APPLE_DEVELOPMENT_TEAM:-}" ]; then
  echo 'CONFIGURATION_REQUIRED: defina APPLE_DEVELOPMENT_TEAM para gerar IPA de distribuição em loja.' >&2
  exit 3
fi

# O Tauri exige uma equipe inclusive no comando de inicialização. No canal
# local-signing isto só permite gerar o projeto Xcode: a compilação abaixo
# desativa explicitamente a assinatura e não usa essa identidade técnica.
if [ "$mode" = 'local-signing' ] && [ -z "${APPLE_DEVELOPMENT_TEAM:-}" ]; then
  export APPLE_DEVELOPMENT_TEAM='PIGE360000'
fi

bash scripts/frontend/install-dependencies.sh
root_dir="$(pwd)"
artifact_dir="$root_dir/release/artifacts/ios"
rm -rf "$artifact_dir"
mkdir -p "$artifact_dir"
version="$(tr -d '[:space:]' < VERSION)"
case "$version" in [0-9]*.[0-9]*.[0-9]*-alpha.[0-9]*) ;; *) echo "Versão alpha inválida para o empacotamento iOS: $version" >&2; exit 4 ;; esac
ios_version="${version%-alpha.*}"
ios_config="{\"version\":\"$ios_version\"}"

initialize_ios_project() {
  app="$1"
  (
    cd "apps/$app"
    if [ "${CI:-false}" = 'true' ]; then rm -rf src-tauri/gen/apple; fi
    if [ ! -d src-tauri/gen/apple ]; then
      ios_platform_config='src-tauri/tauri.ios.conf.json'
      ios_platform_backup="$(mktemp)"
      if [ -f "$ios_platform_config" ]; then cp "$ios_platform_config" "$ios_platform_backup"; fi
      restore_ios_platform_config() {
        if [ -s "$ios_platform_backup" ]; then cp "$ios_platform_backup" "$ios_platform_config"; else rm -f "$ios_platform_config"; fi
        rm -f "$ios_platform_backup"
      }
      trap restore_ios_platform_config EXIT HUP INT TERM
      python3 - "$ios_platform_config" "$ios_version" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
config = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
config["version"] = sys.argv[2]
path.write_text(json.dumps(config), encoding="utf-8")
PY
      npx --no-install tauri ios init --ci
      restore_ios_platform_config
      trap - EXIT HUP INT TERM
    fi
    [ -d src-tauri/gen/apple ] || { echo "Falha ao gerar o projeto iOS para $app." >&2; exit 4; }
  )
}

package_for_local_signing() {
  app="$1"
  project_root="apps/$app/src-tauri/gen/apple"
  project="$(find "$project_root" -type d -name '*.xcodeproj' -print 2>/dev/null | sort | head -n 1)"
  [ -n "$project" ] || { echo "Projeto Xcode não encontrado para $app." >&2; exit 4; }
  scheme="$(xcodebuild -list -project "$project" -json | python3 -c 'import json, sys; data = json.load(sys.stdin); schemes = data.get("project", {}).get("schemes", []); print(schemes[0] if schemes else "")')"
  [ -n "$scheme" ] || { echo "Scheme Xcode não encontrada para $app." >&2; exit 4; }

  (
    cd "apps/$app"
    npm run build
  )
  derived_data="$(mktemp -d "${TMPDIR:-/tmp}/pige360-ios-derived.XXXXXX")"
  xcodebuild \
    -project "$project" \
    -scheme "$scheme" \
    -configuration release \
    -sdk iphoneos \
    -destination 'generic/platform=iOS' \
    -derivedDataPath "$derived_data" \
    CODE_SIGNING_ALLOWED=NO \
    CODE_SIGNING_REQUIRED=NO \
    CODE_SIGN_IDENTITY= \
    DEVELOPMENT_TEAM="$APPLE_DEVELOPMENT_TEAM" \
    build

  app_bundle="$(find "$derived_data/Build/Products" -type d -path '*release-iphoneos/*.app' -print 2>/dev/null | sort | tail -n 1)"
  [ -n "$app_bundle" ] || { echo "Bundle iOS arm64 não encontrado para $app." >&2; exit 4; }
  executable="$(/usr/libexec/PlistBuddy -c 'Print :CFBundleExecutable' "$app_bundle/Info.plist" 2>/dev/null || true)"
  [ -n "$executable" ] && [ -f "$app_bundle/$executable" ] || { echo "Executável iOS ausente no bundle de $app." >&2; exit 4; }
  lipo -archs "$app_bundle/$executable" | tr ' ' '\n' | grep -Fx 'arm64' >/dev/null || {
    echo "Bundle iOS de $app não contém executável arm64." >&2
    exit 4
  }

  work="$(mktemp -d "${TMPDIR:-/tmp}/pige360-ios-ipa.XXXXXX")"
  mkdir -p "$work/Payload"
  cp -R "$app_bundle" "$work/Payload/"
  output="$artifact_dir/${app}-ready-for-local-signing.ipa"
  (cd "$work" && ditto -c -k --sequesterRsrc --keepParent Payload "$output")
  unzip -Z1 "$output" | grep -Eq '^Payload/[^/]+\.app/Info\.plist$' || {
    echo "IPA de $app não possui estrutura Payload/<App>.app." >&2
    exit 4
  }
  rm -rf "$work" "$derived_data"
}

for app in family-app teacher-app student-app admin-app pos-app; do
  initialize_ios_project "$app"
  if [ "$mode" = 'store' ]; then
    (
      cd "apps/$app"
      npx --no-install tauri ios build --target aarch64 --config "$ios_config"
    )
    ipa="$(find "apps/$app/src-tauri/gen/apple/build/arm64" -maxdepth 1 -type f -name '*.ipa' -print 2>/dev/null | sort | tail -n 1)"
    [ -n "$ipa" ] || { echo "IPA não encontrada para $app." >&2; exit 4; }
    cp "$ipa" "$artifact_dir/${app}.ipa"
  else
    package_for_local_signing "$app"
  fi
done

count="$(find "$artifact_dir" -maxdepth 1 -type f -name '*.ipa' | wc -l | tr -d '[:space:]')"
[ "$count" -eq 5 ] || { echo "Esperadas 5 IPAs; encontradas $count." >&2; exit 4; }
(cd "$artifact_dir" && sha256sum ./*.ipa > SHA256SUMS)
if [ "$mode" = 'local-signing' ]; then
  printf 'IPAs iOS arm64 geradas para assinatura local; aplique certificado e perfil de desenvolvimento antes de instalar em aparelho físico.\n'
fi
