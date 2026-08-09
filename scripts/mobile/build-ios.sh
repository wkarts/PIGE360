#!/bin/sh
set -eu
ROOT="$(pwd)"
TAURI_IOS_CLI_VERSION="${PIGE360_TAURI_IOS_CLI_VERSION:-2.11.4}"

command -v xcodebuild >/dev/null 2>&1 || { echo 'Xcode/xcodebuild não disponível.' >&2; exit 3; }
command -v cargo >/dev/null 2>&1 || { echo 'Rust/cargo não disponível.' >&2; exit 3; }
command -v npm >/dev/null 2>&1 || { echo 'npm não disponível.' >&2; exit 3; }

bash scripts/frontend/install-dependencies.sh
rustup target add aarch64-apple-ios x86_64-apple-ios aarch64-apple-ios-sim
mkdir -p release/artifacts/ios
rm -rf release/artifacts/ios/* 2>/dev/null || true

apps="${PIGE360_MOBILE_APPS:-family-app teacher-app student-app admin-app pos-app}"
for app in $apps; do
  app_dir="$ROOT/apps/$app"
  [ -d "$app_dir/src-tauri" ] || { echo "Aplicação Tauri ausente: $app" >&2; exit 4; }

  echo "Preparando Tauri CLI $TAURI_IOS_CLI_VERSION para $app"
  npm install \
    --workspace "./apps/$app" \
    --no-save \
    --package-lock=false \
    --no-audit \
    --no-fund \
    "@tauri-apps/cli@$TAURI_IOS_CLI_VERSION"

  (
    cd "$app_dir"
    if ! find src-tauri/gen/apple -maxdepth 2 -name '*.xcodeproj' -print -quit 2>/dev/null | grep -q .; then
      echo "Inicializando projeto iOS Tauri para $app"
      rm -rf src-tauri/gen/apple src-tauri/gen/ios
      CI=true npx --no-install tauri ios init --ci
    fi

    echo "Compilando iOS ARM64 sem assinatura via Tauri: $app"
    CI=true npx --no-install tauri ios build \
      --ci \
      --target aarch64 \
      --no-sign \
      --ignore-version-mismatches
  )

  app_bundle="$(find "$app_dir/src-tauri" -type d -name '*.app' -print -quit 2>/dev/null || true)"
  [ -n "$app_bundle" ] || { echo "Bundle .app não gerado para $app" >&2; exit 6; }

  tmp="$(mktemp -d)"
  mkdir -p "$tmp/Payload"
  cp -R "$app_bundle" "$tmp/Payload/"
  (cd "$tmp" && /usr/bin/zip -qry "$ROOT/release/artifacts/ios/${app}-unsigned.ipa" Payload)
  rm -rf "$tmp"
  test -s "$ROOT/release/artifacts/ios/${app}-unsigned.ipa"
done

test -n "$(find release/artifacts/ios -type f -name '*.ipa' -print -quit)"
find release/artifacts/ios -maxdepth 1 -type f -name '*.ipa' -print | sort
