#!/bin/sh
set -eu
command -v xcodebuild >/dev/null || { echo 'SKIPPED_NOT_CONFIGURED: Xcode ausente.' >&2; exit 3; }
command -v cargo >/dev/null || { echo 'SKIPPED_NOT_CONFIGURED: Rust ausente.' >&2; exit 3; }
bash scripts/frontend/install-dependencies.sh
mkdir -p release/artifacts/ios
for app in family-app teacher-app student-app admin-app pos-app; do
  (cd "apps/$app" && npx --no-install tauri ios build --target aarch64)
done
find apps -path '*/src-tauri/gen/apple/build/arm64/*.ipa' -type f -exec cp {} release/artifacts/ios/ \;
count="$(find release/artifacts/ios -maxdepth 1 -type f -name '*.ipa' | wc -l | tr -d '[:space:]')"
[ "$count" -eq 5 ] || { echo "Esperadas 5 IPAs unsigned; encontradas $count." >&2; exit 4; }
