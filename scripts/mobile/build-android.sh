#!/bin/sh
set -eu
command -v cargo >/dev/null || { echo 'SKIPPED_NOT_CONFIGURED: Rust ausente.' >&2; exit 3; }
[ -n "${ANDROID_HOME:-}" ] || { echo 'SKIPPED_NOT_CONFIGURED: ANDROID_HOME ausente.' >&2; exit 3; }
bash scripts/frontend/install-dependencies.sh
mkdir -p release/artifacts/android
for app in family-app teacher-app student-app admin-app pos-app kiosk-app timeclock-app; do
  (cd "apps/$app" && npx --no-install tauri android build --apk && npx --no-install tauri android build --aab)
done
find apps -type f \( -name '*.apk' -o -name '*.aab' \) -exec cp {} release/artifacts/android/ \;
