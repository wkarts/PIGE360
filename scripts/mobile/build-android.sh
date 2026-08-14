#!/bin/sh
set -eu
command -v cargo >/dev/null || { echo 'SKIPPED_NOT_CONFIGURED: Rust ausente.' >&2; exit 3; }
[ -n "${ANDROID_HOME:-}" ] || { echo 'SKIPPED_NOT_CONFIGURED: ANDROID_HOME ausente.' >&2; exit 3; }
[ -n "${NDK_HOME:-}" ] || { echo 'SKIPPED_NOT_CONFIGURED: NDK_HOME ausente.' >&2; exit 3; }
[ -d "$NDK_HOME" ] || { echo "SKIPPED_NOT_CONFIGURED: NDK_HOME inválido: $NDK_HOME" >&2; exit 3; }
ndk_host_tag=''
case "$(uname -s)" in
  Linux) ndk_host_tag='linux-x86_64' ;;
  Darwin)
    case "$(uname -m)" in
      arm64) ndk_host_tag='darwin-arm64' ;;
      *) ndk_host_tag='darwin-x86_64' ;;
    esac
    ;;
  *) echo "Host Android NDK não suportado: $(uname -s)" >&2; exit 3 ;;
esac
ndk_bin="$NDK_HOME/toolchains/llvm/prebuilt/$ndk_host_tag/bin"
[ -d "$ndk_bin" ] || { echo "Toolchain NDK ausente: $ndk_bin" >&2; exit 3; }
[ -x "$ndk_bin/llvm-ar" ] && [ -x "$ndk_bin/llvm-ranlib" ] || {
  echo "Ferramentas llvm-ar/llvm-ranlib ausentes no NDK: $ndk_bin" >&2
  exit 3
}
# O OpenSSL invocado por dependências Rust procura <target>-ranlib, nomes que
# o NDK atual substituiu pelos binários LLVM genéricos. Os shims são efêmeros,
# exclusivos da execução e não alteram o SDK do runner.
android_toolshim="$(mktemp -d "${TMPDIR:-/tmp}/pige360-android-tools.XXXXXX")"
trap 'rm -rf "$android_toolshim"' 0 HUP INT TERM
for target in aarch64-linux-android arm-linux-androideabi armv7-linux-androideabi i686-linux-android x86_64-linux-android; do
  ln -s "$ndk_bin/llvm-ar" "$android_toolshim/$target-ar"
  ln -s "$ndk_bin/llvm-ranlib" "$android_toolshim/$target-ranlib"
done
export PATH="$android_toolshim:$ndk_bin:$PATH"
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
    [ -d src-tauri/gen/android/app ] || {
      echo "Falha ao gerar o projeto Android para $app." >&2
      exit 4
    }
    npx --no-install tauri android build --apk
    npx --no-install tauri android build --aab
  )
done
find apps -type f \( -name '*.apk' -o -name '*.aab' \) -exec cp {} release/artifacts/android/ \;
apk_count="$(find release/artifacts/android -maxdepth 1 -type f -name '*.apk' | wc -l | tr -d '[:space:]')"
aab_count="$(find release/artifacts/android -maxdepth 1 -type f -name '*.aab' | wc -l | tr -d '[:space:]')"
[ "$apk_count" -eq 7 ] || { echo "Esperados 7 APKs; encontrados $apk_count." >&2; exit 4; }
[ "$aab_count" -eq 7 ] || { echo "Esperados 7 AABs; encontrados $aab_count." >&2; exit 4; }
