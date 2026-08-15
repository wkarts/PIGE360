#!/bin/sh
set -eu

usage() {
  cat <<'EOF'
Uso: scripts/mobile/build-ios.sh [--mode <local-signing|store>] [--app <nome|all>]
EOF
}

mode='store'
app_scope='all'
while [ "$#" -gt 0 ]; do
  case "$1" in
    --mode) mode="${2:?Informe o modo após --mode}"; shift 2 ;;
    --app) app_scope="${2:?Informe o app após --app}"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Argumento iOS desconhecido: $1" >&2; usage >&2; exit 2 ;;
  esac
done

case "$mode" in
  local-signing|store) ;;
  *) echo "Modo iOS inválido: $mode" >&2; exit 2 ;;
esac
case "$app_scope" in
  all|family-app|teacher-app|student-app|admin-app|pos-app) ;;
  *) echo "App iOS inválido: $app_scope" >&2; exit 2 ;;
esac

command -v xcodebuild >/dev/null || { echo 'SKIPPED_NOT_CONFIGURED: Xcode ausente.' >&2; exit 3; }
command -v cargo >/dev/null || { echo 'SKIPPED_NOT_CONFIGURED: Rust ausente.' >&2; exit 3; }
command -v zip >/dev/null || { echo 'SKIPPED_NOT_CONFIGURED: zip ausente.' >&2; exit 3; }
command -v lipo >/dev/null || { echo 'SKIPPED_NOT_CONFIGURED: lipo ausente.' >&2; exit 3; }
command -v python3 >/dev/null || { echo 'SKIPPED_NOT_CONFIGURED: Python 3 ausente.' >&2; exit 3; }
command -v unzip >/dev/null || { echo 'SKIPPED_NOT_CONFIGURED: unzip ausente.' >&2; exit 3; }

if [ "$mode" = 'store' ] && [ -z "${APPLE_DEVELOPMENT_TEAM:-}" ]; then
  echo 'CONFIGURATION_REQUIRED: defina APPLE_DEVELOPMENT_TEAM para gerar IPA de distribuição em loja.' >&2
  exit 3
fi

# O Tauri exige uma equipe inclusive no comando de inicialização. No canal
# local-signing isto só permite gerar o projeto Xcode: sem assinatura faz o
# arquivamento sem certificado e sem perfil de provisionamento.
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

verify_local_signing_ipa() {
  app="$1"
  ipa="$2"
  work="$(mktemp -d "${TMPDIR:-/tmp}/pige360-ios-ipa.XXXXXX")"
  if ! unzip -qq "$ipa" -d "$work"; then
    rm -rf "$work"
    echo "IPA de $app não é um arquivo ZIP válido." >&2
    exit 4
  fi
  [ -d "$work/Payload" ] || {
    rm -rf "$work"
    echo "IPA de $app não possui estrutura Payload/<App>.app." >&2
    exit 4
  }
  app_bundle="$(find "$work/Payload" -maxdepth 1 -type d -name '*.app' -print 2>/dev/null | sort | tail -n 1)"
  [ -n "$app_bundle" ] || { echo "Bundle iOS não encontrado no IPA de $app." >&2; exit 4; }
  executable="$(/usr/libexec/PlistBuddy -c 'Print :CFBundleExecutable' "$app_bundle/Info.plist" 2>/dev/null || true)"
  [ -n "$executable" ] && [ -f "$app_bundle/$executable" ] || { echo "Executável iOS ausente no IPA de $app." >&2; exit 4; }
  lipo -archs "$app_bundle/$executable" | tr ' ' '\n' | grep -Fx 'arm64' >/dev/null || {
    echo "IPA de $app não contém executável arm64." >&2
    exit 4
  }
  rm -rf "$work"
}

ios_runtime_config_backup=''
ios_runtime_config_path=''

prepare_ios_runtime_config() {
  app="$1"
  ios_runtime_config_path="$root_dir/apps/$app/src-tauri/tauri.conf.json"
  ios_runtime_config_backup="$(mktemp "${TMPDIR:-/tmp}/pige360-ios-config.XXXXXX")"
  cp "$ios_runtime_config_path" "$ios_runtime_config_backup"
  python3 - "$ios_runtime_config_path" "$ios_version" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
config = json.loads(path.read_text(encoding="utf-8"))
config["version"] = sys.argv[2]
path.write_text(json.dumps(config), encoding="utf-8")
PY
}

restore_ios_runtime_config() {
  if [ -n "$ios_runtime_config_backup" ] && [ -f "$ios_runtime_config_backup" ]; then
    cp "$ios_runtime_config_backup" "$ios_runtime_config_path"
    rm -f "$ios_runtime_config_backup"
  fi
  ios_runtime_config_backup=''
  ios_runtime_config_path=''
}

tauri_options_pid=''
tauri_options_log=''
cleanup_tauri_options() {
  if [ -n "$tauri_options_pid" ] && kill -0 "$tauri_options_pid" 2>/dev/null; then
    kill "$tauri_options_pid" 2>/dev/null || true
    wait "$tauri_options_pid" 2>/dev/null || true
  fi
  tauri_options_pid=''
  [ -z "$tauri_options_log" ] || rm -f "$tauri_options_log"
  tauri_options_log=''
}
cleanup_ios_build() {
  cleanup_tauri_options
  restore_ios_runtime_config
}
trap cleanup_ios_build EXIT HUP INT TERM

start_tauri_options_server() {
  app="$1"
  app_dir="$root_dir/apps/$app"
  identifier="$(python3 - "$app_dir/src-tauri/tauri.conf.json" <<'PY'
import json
import sys
from pathlib import Path

print(json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))["identifier"])
PY
)"
  server_addr="${TMPDIR:-/tmp}/${identifier}-server-addr"
  tauri_options_log="$(mktemp "${TMPDIR:-/tmp}/pige360-ios-options.XXXXXX")"
  (
    cd "$app_dir"
    npx --no-install tauri ios build --target aarch64 --open --config "$ios_config" >"$tauri_options_log" 2>&1 &
    printf '%s' "$!" >"$tauri_options_log.pid"
  )
  tauri_options_pid="$(cat "$tauri_options_log.pid")"
  rm -f "$tauri_options_log.pid"

  attempts=0
  while [ ! -s "$server_addr" ]; do
    if ! kill -0 "$tauri_options_pid" 2>/dev/null; then
      cat "$tauri_options_log" >&2 || true
      echo "O Tauri não iniciou o servidor de opções iOS para $app." >&2
      return 4
    fi
    attempts=$((attempts + 1))
    if [ "$attempts" -ge 60 ]; then
      cat "$tauri_options_log" >&2 || true
      echo "Tempo esgotado ao iniciar as opções iOS do Tauri para $app." >&2
      return 4
    fi
    sleep 1
  done
}

package_for_local_signing() {
  app="$1"
  app_dir="$root_dir/apps/$app"
  project_root="$app_dir/src-tauri/gen/apple"
  project="$(find "$project_root" -type d -name '*.xcodeproj' -print 2>/dev/null | sort | head -n 1)"
  [ -n "$project" ] || { echo "Projeto Xcode não encontrado para $app." >&2; exit 4; }
  scheme="$(xcodebuild -list -project "$project" -json | python3 -c 'import json, sys; data = json.load(sys.stdin); schemes = data.get("project", {}).get("schemes", []); print(schemes[0] if schemes else "")')"
  [ -n "$scheme" ] || { echo "Scheme Xcode não encontrada para $app." >&2; exit 4; }

  # Tauri CLI 2.3.1 não oferece uma flag para suprimir assinatura. --open
  # mantém o servidor de opções exigido pelo build phase enquanto xcodebuild
  # compila com assinatura explicitamente desligada.
  start_tauri_options_server "$app"
  derived_root="$(mktemp -d "${TMPDIR:-/tmp}/pige360-ios-derived.XXXXXX")"
  derived_data="$derived_root/DerivedData"
  if ! (
    cd "$app_dir"
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
  ); then
    cleanup_tauri_options
    rm -rf "$derived_root"
    echo "Falha ao construir o bundle iOS sem assinatura para $app." >&2
    return 4
  fi
  cleanup_tauri_options

  app_bundle="$(find "$derived_data/Build/Products" -type d -path '*release-iphoneos/*.app' -print 2>/dev/null | sort | tail -n 1)"
  [ -n "$app_bundle" ] || { echo "Bundle iOS arm64 não encontrado para $app." >&2; rm -rf "$derived_root"; exit 4; }
  executable="$(/usr/libexec/PlistBuddy -c 'Print :CFBundleExecutable' "$app_bundle/Info.plist" 2>/dev/null || true)"
  [ -n "$executable" ] && [ -f "$app_bundle/$executable" ] || { echo "Executável iOS ausente no bundle de $app." >&2; rm -rf "$derived_root"; exit 4; }
  lipo -archs "$app_bundle/$executable" | tr ' ' '\n' | grep -Fx 'arm64' >/dev/null || {
    echo "Bundle iOS de $app não contém executável arm64." >&2
    rm -rf "$derived_root"
    exit 4
  }
  [ ! -e "$app_bundle/embedded.mobileprovision" ] || {
    echo "O bundle iOS de $app contém provisioning profile, mas local-signing não aceita credenciais no CI." >&2
    rm -rf "$derived_root"
    exit 4
  }

  work="$(mktemp -d "${TMPDIR:-/tmp}/pige360-ios-ipa.XXXXXX")"
  mkdir -p "$work/Payload"
  cp -R "$app_bundle" "$work/Payload/"
  output="$artifact_dir/${app}-ready-for-local-signing.ipa"
  (cd "$work" && zip -qry "$output" Payload)
  rm -rf "$work" "$derived_root"
  verify_local_signing_ipa "$app" "$output"
}

if [ "$app_scope" = 'all' ]; then
  apps='family-app teacher-app student-app admin-app pos-app'
  expected_count=5
else
  apps="$app_scope"
  expected_count=1
fi

for app in $apps; do
  initialize_ios_project "$app"
  # O xcode-script do Tauri 2.3 lê tauri.conf.json antes de reaplicar --config.
  # A cópia temporária contém a versão CFBundle numérica e é sempre restaurada.
  prepare_ios_runtime_config "$app"
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
  restore_ios_runtime_config
done

count="$(find "$artifact_dir" -maxdepth 1 -type f -name '*.ipa' | wc -l | tr -d '[:space:]')"
[ "$count" -eq "$expected_count" ] || { echo "Esperadas $expected_count IPAs; encontradas $count." >&2; exit 4; }
(cd "$artifact_dir" && sha256sum ./*.ipa > SHA256SUMS)
if [ "$mode" = 'local-signing' ]; then
  printf 'IPAs iOS arm64 geradas para assinatura local; aplique certificado e perfil de desenvolvimento antes de instalar em aparelho físico.\n'
fi
