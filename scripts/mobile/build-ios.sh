#!/bin/sh
set -eu
ROOT="$(pwd)"
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
  (
    cd "$app_dir"
    if ! find src-tauri/gen/apple -maxdepth 2 -name '*.xcodeproj' -print -quit 2>/dev/null | grep -q .; then
      echo "Inicializando projeto iOS Tauri para $app"
      rm -rf src-tauri/gen/apple src-tauri/gen/ios
      CI=true npx --no-install tauri ios init --ci
    fi
    npm run build
  )

  project="$(find "$app_dir/src-tauri/gen/apple" -maxdepth 1 -name '*.xcodeproj' -print -quit)"
  [ -n "$project" ] || { echo "Projeto Xcode não gerado para $app" >&2; exit 5; }
  workspace="$project/project.xcworkspace"
  scheme="$(basename "$project" .xcodeproj)_iOS"
  derived="$app_dir/src-tauri/gen/apple/DerivedData"
  rm -rf "$derived"

  echo "Compilando iOS ARM64 sem assinatura: $app / $scheme"
  xcodebuild \
    -workspace "$workspace" \
    -scheme "$scheme" \
    -sdk iphoneos \
    -configuration release \
    -destination 'generic/platform=iOS' \
    -derivedDataPath "$derived" \
    CODE_SIGNING_ALLOWED=NO \
    CODE_SIGNING_REQUIRED=NO \
    CODE_SIGN_IDENTITY='' \
    DEVELOPMENT_TEAM='' \
    ARCHS=arm64 \
    ONLY_ACTIVE_ARCH=NO \
    build

  app_bundle="$(find "$derived/Build/Products" -type d -name '*.app' -print -quit 2>/dev/null || true)"
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
