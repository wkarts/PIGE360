#!/bin/sh
set -eu
command -v cargo >/dev/null 2>&1 || { echo 'Rust/cargo não disponível.' >&2; exit 3; }
command -v npm >/dev/null 2>&1 || { echo 'npm não disponível.' >&2; exit 3; }
[ -n "${ANDROID_HOME:-}" ] || { echo 'ANDROID_HOME não configurado.' >&2; exit 3; }

NDK_HOME="${NDK_HOME:-${ANDROID_NDK_HOME:-${ANDROID_NDK_ROOT:-${ANDROID_NDK:-}}}}"
[ -n "$NDK_HOME" ] && [ -d "$NDK_HOME" ] || { echo 'Android NDK não encontrado no runner.' >&2; exit 3; }
export NDK_HOME
export ANDROID_NDK_HOME="${ANDROID_NDK_HOME:-$NDK_HOME}"
export ANDROID_NDK_ROOT="${ANDROID_NDK_ROOT:-$NDK_HOME}"
export ANDROID_NDK="${ANDROID_NDK:-$NDK_HOME}"

echo "Android SDK: $ANDROID_HOME"
echo "Android NDK: $NDK_HOME"

bash scripts/frontend/install-dependencies.sh
rustup target add aarch64-linux-android armv7-linux-androideabi i686-linux-android x86_64-linux-android
mkdir -p release/artifacts/android
rm -f release/artifacts/android/*.apk release/artifacts/android/*.aab 2>/dev/null || true

apps="${PIGE360_MOBILE_APPS:-family-app teacher-app student-app admin-app pos-app kiosk-app timeclock-app}"
for app in $apps; do
  [ -d "apps/$app/src-tauri" ] || { echo "Aplicação Tauri ausente: $app" >&2; exit 4; }
  (
    cd "apps/$app"
    if [ ! -f src-tauri/gen/android/gradlew ]; then
      echo "Inicializando projeto Android Tauri para $app"
      rm -rf src-tauri/gen/android
      CI=true npx --no-install tauri android init --ci
    fi
    test -f src-tauri/gen/android/gradlew
    echo "Compilando APK/AAB: $app"
    CI=true npx --no-install tauri android build --ci
  )
  found=0
  while IFS= read -r file; do
    [ -n "$file" ] || continue
    found=1
    cp "$file" "release/artifacts/android/${app}-$(basename "$file")"
  done <<EOF
$(find "apps/$app/src-tauri/gen/android" -type f \( -name '*.apk' -o -name '*.aab' \) 2>/dev/null | sort)
EOF
  [ "$found" -eq 1 ] || { echo "Nenhum APK/AAB gerado para $app" >&2; exit 5; }
done

test -n "$(find release/artifacts/android -type f \( -name '*.apk' -o -name '*.aab' \) -print -quit)"
find release/artifacts/android -maxdepth 1 -type f -print | sort
