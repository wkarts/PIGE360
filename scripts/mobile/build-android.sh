#!/bin/sh
set -eu
command -v cargo >/dev/null || { echo 'SKIPPED_NOT_CONFIGURED: Rust ausente.' >&2; exit 3; }
[ -n "${ANDROID_HOME:-}" ] || { echo 'SKIPPED_NOT_CONFIGURED: ANDROID_HOME ausente.' >&2; exit 3; }
bash scripts/frontend/install-dependencies.sh
mkdir -p release/artifacts/android
for app in family-app teacher-app student-app admin-app pos-app kiosk-app timeclock-app; do
  (
    cd "apps/$app"
    # A árvore Android é gerada pelo Tauri. Em CI ela sempre parte do config
    # canônico, evitando fontes Java antigas quando o identificador mudou.
    if [ "${CI:-false}" = "true" ]; then
      rm -rf src-tauri/gen/android
    fi
    if [ ! -d src-tauri/gen/android/app ]; then
      npx --no-install tauri android init --ci --skip-targets-install
    fi
    npx --no-install tauri android build --apk
    npx --no-install tauri android build --aab
  )
done
find apps -type f \( -name '*.apk' -o -name '*.aab' \) -exec cp {} release/artifacts/android/ \;
apk_count="$(find release/artifacts/android -maxdepth 1 -type f -name '*.apk' | wc -l | tr -d '[:space:]')"
aab_count="$(find release/artifacts/android -maxdepth 1 -type f -name '*.aab' | wc -l | tr -d '[:space:]')"
[ "$apk_count" -eq 7 ] || { echo "Esperados 7 APKs; encontrados $apk_count." >&2; exit 4; }
[ "$aab_count" -eq 7 ] || { echo "Esperados 7 AABs; encontrados $aab_count." >&2; exit 4; }
