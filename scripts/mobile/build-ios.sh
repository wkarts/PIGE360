#!/bin/sh
set -eu
command -v xcodebuild >/dev/null || { echo 'SKIPPED_NOT_CONFIGURED: Xcode ausente.' >&2; exit 3; }
command -v cargo >/dev/null || { echo 'SKIPPED_NOT_CONFIGURED: Rust ausente.' >&2; exit 3; }
bash scripts/frontend/install-dependencies.sh
mkdir -p release/artifacts/ios
for app in family-app teacher-app student-app admin-app pos-app; do
  (cd "apps/$app" && npx --no-install tauri ios build --target aarch64)
done
echo 'A montagem de .xcarchive e IPA unsigned usa scripts/mobile/package-ios-unsigned.sh no macOS.'
