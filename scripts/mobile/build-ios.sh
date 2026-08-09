#!/bin/sh
set -eu
ROOT="$(pwd)"
TAURI_IOS_CLI_VERSION="${PIGE360_TAURI_IOS_CLI_VERSION:-2.11.4}"

command -v xcodebuild >/dev/null 2>&1 || { echo 'Xcode/xcodebuild não disponível.' >&2; exit 3; }
command -v cargo >/dev/null 2>&1 || { echo 'Rust/cargo não disponível.' >&2; exit 3; }
command -v npm >/dev/null 2>&1 || { echo 'npm não disponível.' >&2; exit 3; }
command -v node >/dev/null 2>&1 || { echo 'Node.js não disponível.' >&2; exit 3; }

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

    # O projeto gerado pelo Tauri executa o script npm `tauri` também dentro
    # do build phase do Xcode. Para manter o processo pai e o xcode-script na
    # mesma CLI (e obter --no-sign), fazemos override somente no workspace
    # efêmero do runner. Nenhum lockfile é alterado ou versionado.
    node - "$TAURI_IOS_CLI_VERSION" <<'NODE'
const fs = require('fs');
const version = process.argv[2];
const file = 'package.json';
const pkg = JSON.parse(fs.readFileSync(file, 'utf8'));
pkg.scripts = pkg.scripts || {};
pkg.scripts.tauri = `npx --yes --package=@tauri-apps/cli@${version} tauri`;
fs.writeFileSync(file, `${JSON.stringify(pkg, null, 2)}\n`);
NODE

    echo "Usando Tauri CLI $TAURI_IOS_CLI_VERSION para $app"
    npm run tauri -- --version

    if ! find src-tauri/gen/apple -maxdepth 2 -name '*.xcodeproj' -print -quit 2>/dev/null | grep -q .; then
      echo "Inicializando projeto iOS Tauri para $app"
      rm -rf src-tauri/gen/apple src-tauri/gen/ios
      CI=true npm run tauri -- ios init --ci
    fi

    echo "Compilando iOS ARM64 sem assinatura via Tauri: $app"
    CI=true npm run tauri -- ios build \
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
