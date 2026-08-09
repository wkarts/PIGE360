#!/bin/sh
set -eu
manifest="${1:?manifest obrigatório}"
app="${2:?app obrigatório}"
platform="${3:?plataforma obrigatória}"

PYTHON_BIN="${PYTHON_BIN:-}"
if [ -z "$PYTHON_BIN" ]; then
  if command -v python3 >/dev/null 2>&1; then PYTHON_BIN=python3; else PYTHON_BIN=python; fi
fi
"$PYTHON_BIN" scripts/validation/tenant_app_manifest.py "$manifest"

app_dir="apps/${app}-app"
[ -d "$app_dir" ] || app_dir="apps/${app}"
[ -d "$app_dir" ] || { echo "Aplicação não encontrada para tenant: $app" >&2; exit 4; }
app_name="$(basename "$app_dir")"
out="release/artifacts/tenant-apps/$app/$platform"
rm -rf "$out"
mkdir -p "$out"

case "$platform" in
  pwa)
    bash scripts/frontend/install-dependencies.sh
    npm --workspace "./$app_dir" run build
    [ -d "$app_dir/dist" ] || { echo "Dist PWA ausente para $app" >&2; exit 5; }
    cp -R "$app_dir/dist"/. "$out/"
    ;;
  android)
    PIGE360_MOBILE_APPS="$app_name" bash scripts/mobile/build-android.sh
    cp release/artifacts/android/${app_name}-*.apk "$out/" 2>/dev/null || true
    cp release/artifacts/android/${app_name}-*.aab "$out/" 2>/dev/null || true
    test -n "$(find "$out" -type f \( -name '*.apk' -o -name '*.aab' \) -print -quit)"
    ;;
  ios)
    PIGE360_MOBILE_APPS="$app_name" bash scripts/mobile/build-ios.sh
    cp release/artifacts/ios/${app_name}-*.ipa "$out/" 2>/dev/null || true
    test -n "$(find "$out" -type f -name '*.ipa' -print -quit)"
    ;;
  windows|linux|macos)
    command -v cargo >/dev/null 2>&1 || { echo 'cargo não disponível.' >&2; exit 3; }
    command -v npm >/dev/null 2>&1 || { echo 'npm não disponível.' >&2; exit 3; }
    bash scripts/frontend/install-dependencies.sh
    case "$platform" in
      windows) target="${TAURI_TARGET:-x86_64-pc-windows-msvc}" ;;
      linux) target="${TAURI_TARGET:-x86_64-unknown-linux-gnu}" ;;
      macos) target="${TAURI_TARGET:-aarch64-apple-darwin}" ;;
    esac
    rustup target add "$target"
    (cd "$app_dir" && npx --no-install tauri build --target "$target")
    while IFS= read -r file; do
      [ -n "$file" ] || continue
      cp "$file" "$out/$(basename "$file")"
    done <<EOF
$(find "$app_dir/src-tauri/target/$target/release/bundle" -type f 2>/dev/null | sort)
EOF
    test -n "$(find "$out" -type f -print -quit)"
    ;;
  *) echo "Plataforma inválida: $platform" >&2; exit 2 ;;
esac

printf 'tenant=%s platform=%s artifacts=%s\n' "$app" "$platform" "$(find "$out" -type f | wc -l | tr -d ' ')"
