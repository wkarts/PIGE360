#!/bin/sh
set -eu
ROOT="$(pwd)"
command -v cargo >/dev/null 2>&1 || { echo 'Rust/cargo não disponível.' >&2; exit 3; }
command -v npm >/dev/null 2>&1 || { echo 'npm não disponível.' >&2; exit 3; }
[ -n "${ANDROID_HOME:-}" ] || { echo 'ANDROID_HOME não configurado.' >&2; exit 3; }

NDK_HOME="${NDK_HOME:-${ANDROID_NDK_HOME:-${ANDROID_NDK_ROOT:-${ANDROID_NDK:-}}}}"
[ -n "$NDK_HOME" ] && [ -d "$NDK_HOME" ] || { echo 'Android NDK não encontrado no runner.' >&2; exit 3; }
export NDK_HOME
export ANDROID_NDK_HOME="${ANDROID_NDK_HOME:-$NDK_HOME}"
export ANDROID_NDK_ROOT="${ANDROID_NDK_ROOT:-$NDK_HOME}"
export ANDROID_NDK="${ANDROID_NDK:-$NDK_HOME}"

case "$(uname -s)" in
  Linux) ndk_host="linux-x86_64" ;;
  Darwin) ndk_host="darwin-x86_64" ;;
  *) echo "Host não suportado para o Android NDK: $(uname -s)" >&2; exit 3 ;;
esac

ndk_bin="$NDK_HOME/toolchains/llvm/prebuilt/$ndk_host/bin"
[ -d "$ndk_bin" ] || { echo "Toolchain LLVM do NDK não encontrado: $ndk_bin" >&2; exit 3; }
[ -x "$ndk_bin/llvm-ar" ] || { echo 'llvm-ar não encontrado no Android NDK.' >&2; exit 3; }
[ -x "$ndk_bin/llvm-ranlib" ] || { echo 'llvm-ranlib não encontrado no Android NDK.' >&2; exit 3; }

alias_dir="${RUNNER_TEMP:-$ROOT/.tmp}/pige360-android-llvm-bin"
mkdir -p "$alias_dir"
for prefix in aarch64-linux-android arm-linux-androideabi i686-linux-android x86_64-linux-android; do
  ln -sf "$ndk_bin/llvm-ar" "$alias_dir/${prefix}-ar"
  ln -sf "$ndk_bin/llvm-ranlib" "$alias_dir/${prefix}-ranlib"
  [ ! -x "$ndk_bin/llvm-nm" ] || ln -sf "$ndk_bin/llvm-nm" "$alias_dir/${prefix}-nm"
  [ ! -x "$ndk_bin/llvm-strip" ] || ln -sf "$ndk_bin/llvm-strip" "$alias_dir/${prefix}-strip"
done

export AR="$ndk_bin/llvm-ar"
export RANLIB="$ndk_bin/llvm-ranlib"
export PATH="$alias_dir:$ndk_bin:$PATH"

echo "Android SDK: $ANDROID_HOME"
echo "Android NDK: $NDK_HOME"
echo "Android LLVM: $ndk_bin"
echo "Android ranlib: $(command -v aarch64-linux-android-ranlib)"

bash scripts/frontend/install-dependencies.sh
rustup target add aarch64-linux-android armv7-linux-androideabi i686-linux-android x86_64-linux-android
mkdir -p release/artifacts/android
rm -f release/artifacts/android/*.apk release/artifacts/android/*.aab 2>/dev/null || true

apps="${PIGE360_MOBILE_APPS:-family-app teacher-app student-app admin-app pos-app kiosk-app timeclock-app}"
target_root="${PIGE360_ANDROID_CARGO_TARGET_ROOT:-$ROOT/.pige360-build/android-target}"
mkdir -p "$target_root"

for app in $apps; do
  [ -d "apps/$app/src-tauri" ] || { echo "Aplicação Tauri ausente: $app" >&2; exit 4; }

  # O codegen Android do Tauri produz TauriActivity/WryActivity com package
  # específico do aplicativo. Não é seguro compartilhar CARGO_TARGET_DIR entre
  # apps diferentes: Cargo pode reaproveitar o build-script do primeiro app e
  # deixar o segundo sem TauriActivity.kt.
  app_target_dir="$target_root/$app"
  mkdir -p "$app_target_dir"
  (
    export CARGO_TARGET_DIR="$app_target_dir"
    cd "apps/$app"

    # Sempre gere o projeto Android a partir da CLI da árvore atual. O diretório
    # gen é artefato efêmero e não deve carregar codegen de execução anterior.
    echo "Inicializando projeto Android Tauri para $app"
    rm -rf src-tauri/gen/android
    CI=true npx --no-install tauri android init --ci
    test -f src-tauri/gen/android/gradlew

    echo "Compilando APK/AAB: $app"
    echo "Cargo target isolado: $CARGO_TARGET_DIR"
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
