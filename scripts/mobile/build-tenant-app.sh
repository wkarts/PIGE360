#!/bin/sh
set -eu
manifest="${1:?manifest obrigatório}"; app="${2:?app obrigatório}"; platform="${3:?plataforma obrigatória}"
python3 scripts/validation/tenant_app_manifest.py "$manifest"
mkdir -p "release/artifacts/tenant-apps/$app/$platform"
case "$platform" in
  android) exec bash scripts/mobile/build-android.sh ;;
  ios) exec bash scripts/mobile/build-ios.sh ;;
  windows|linux|macos) exec bash scripts/desktop/build-all.sh "${TAURI_TARGET:?TAURI_TARGET obrigatório}" ;;
  pwa)
    bash scripts/frontend/install-dependencies.sh
    npm --workspace "./apps/${app}-app" run build 2>/dev/null || npm --workspace "./apps/${app}" run build
    src="apps/${app}-app/dist"; [ -d "$src" ] || src="apps/${app}/dist"
    cp -R "$src"/. "release/artifacts/tenant-apps/$app/$platform/"
    ;;
  *) echo "Plataforma inválida: $platform" >&2; exit 2 ;;
esac
