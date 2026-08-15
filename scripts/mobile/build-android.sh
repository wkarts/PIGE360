#!/bin/sh
set -eu

usage() {
  cat <<'EOF'
Uso: scripts/mobile/build-android.sh [--app <nome|all>] [--profile <debug|release>] [--artifacts <apk|aab|both>] [--verify-signature]
EOF
}

apps='family-app teacher-app student-app admin-app pos-app kiosk-app timeclock-app'
selected_app='all'
profile='release'
artifacts='both'
verify_signature='false'

while [ "$#" -gt 0 ]; do
  case "$1" in
    --app) selected_app="${2:?Informe o aplicativo após --app}"; shift 2 ;;
    --profile) profile="${2:?Informe o perfil após --profile}"; shift 2 ;;
    --artifacts) artifacts="${2:?Informe os artefatos após --artifacts}"; shift 2 ;;
    --verify-signature) verify_signature='true'; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Argumento Android desconhecido: $1" >&2; usage >&2; exit 2 ;;
  esac
done

case " $apps " in
  *" $selected_app "*) selected_apps="$selected_app" ;;
  *) [ "$selected_app" = 'all' ] && selected_apps="$apps" || {
    echo "Aplicativo Android inválido: $selected_app" >&2; exit 2;
  } ;;
esac
case "$profile" in debug|release) ;; *) echo "Perfil Android inválido: $profile" >&2; exit 2 ;; esac
case "$artifacts" in apk|aab|both) ;; *) echo "Tipo de artefato Android inválido: $artifacts" >&2; exit 2 ;; esac

command -v cargo >/dev/null || { echo 'SKIPPED_NOT_CONFIGURED: Rust ausente.' >&2; exit 3; }
[ -n "${ANDROID_HOME:-}" ] || { echo 'SKIPPED_NOT_CONFIGURED: ANDROID_HOME ausente.' >&2; exit 3; }
[ -n "${NDK_HOME:-}" ] || { echo 'SKIPPED_NOT_CONFIGURED: NDK_HOME ausente.' >&2; exit 3; }
[ -d "$NDK_HOME" ] || { echo "SKIPPED_NOT_CONFIGURED: NDK_HOME inválido: $NDK_HOME" >&2; exit 3; }

case "$(uname -s)" in
  Linux) ndk_host_tag='linux-x86_64' ;;
  Darwin)
    case "$(uname -m)" in arm64) ndk_host_tag='darwin-arm64' ;; *) ndk_host_tag='darwin-x86_64' ;; esac ;;
  *) echo "Host Android NDK não suportado: $(uname -s)" >&2; exit 3 ;;
esac
ndk_bin="$NDK_HOME/toolchains/llvm/prebuilt/$ndk_host_tag/bin"
[ -d "$ndk_bin" ] || { echo "Toolchain NDK ausente: $ndk_bin" >&2; exit 3; }
[ -x "$ndk_bin/llvm-ar" ] && [ -x "$ndk_bin/llvm-ranlib" ] || {
  echo "Ferramentas llvm-ar/llvm-ranlib ausentes no NDK: $ndk_bin" >&2; exit 3;
}

android_toolshim="$(mktemp -d "${TMPDIR:-/tmp}/pige360-android-tools.XXXXXX")"
trap 'rm -rf "$android_toolshim"' 0 HUP INT TERM
for target in aarch64-linux-android arm-linux-androideabi armv7-linux-androideabi i686-linux-android x86_64-linux-android; do
  ln -s "$ndk_bin/llvm-ar" "$android_toolshim/$target-ar"
  ln -s "$ndk_bin/llvm-ranlib" "$android_toolshim/$target-ranlib"
done
export PATH="$android_toolshim:$ndk_bin:$PATH"

root_dir="$(pwd)"
artifact_dir="$root_dir/release/artifacts/android"
rm -rf "$artifact_dir"
mkdir -p "$artifact_dir"
bash scripts/frontend/install-dependencies.sh

wants_apk='false'
wants_aab='false'
case "$artifacts" in apk|both) wants_apk='true' ;; esac
case "$artifacts" in aab|both) wants_aab='true' ;; esac
build_profile_args=''
[ "$profile" = 'debug' ] && build_profile_args='--debug'

copy_output() {
  app="$1"
  extension="$2"
  output="$(find "apps/$app/src-tauri/gen/android" -type f -name "*.$extension" -print | sort | tail -n 1)"
  [ -n "$output" ] || { echo "Artefato .$extension não encontrado para $app." >&2; exit 4; }
  cp "$output" "$artifact_dir/${app}-${profile}.$extension"
}

for app in $selected_apps; do
  (
    cd "apps/$app"
    # A árvore Android é gerada pelo Tauri. Em CI ela sempre parte do config
    # canônico, evitando fontes Java antigas quando o identificador mudou.
    if [ "${CI:-false}" = 'true' ]; then rm -rf src-tauri/gen/android; fi
    if [ ! -d src-tauri/gen/android/app ]; then npx --no-install tauri android init --ci --skip-targets-install; fi
    [ -d src-tauri/gen/android/app ] || { echo "Falha ao gerar o projeto Android para $app." >&2; exit 4; }
    [ "$wants_apk" = 'true' ] && npx --no-install tauri android build --apk $build_profile_args
    [ "$wants_aab" = 'true' ] && npx --no-install tauri android build --aab $build_profile_args
  )
  [ "$wants_apk" = 'true' ] && copy_output "$app" apk
  [ "$wants_aab" = 'true' ] && copy_output "$app" aab
done

expected_count="$(printf '%s\n' "$selected_apps" | wc -w | tr -d '[:space:]')"
apk_count="$(find "$artifact_dir" -maxdepth 1 -type f -name '*.apk' | wc -l | tr -d '[:space:]')"
aab_count="$(find "$artifact_dir" -maxdepth 1 -type f -name '*.aab' | wc -l | tr -d '[:space:]')"
[ "$wants_apk" = 'false' ] || [ "$apk_count" -eq "$expected_count" ] || { echo "Esperados $expected_count APKs; encontrados $apk_count." >&2; exit 4; }
[ "$wants_aab" = 'false' ] || [ "$aab_count" -eq "$expected_count" ] || { echo "Esperados $expected_count AABs; encontrados $aab_count." >&2; exit 4; }

if [ "$verify_signature" = 'true' ]; then
  apksigner="$(command -v apksigner || find "$ANDROID_HOME/build-tools" -type f -name apksigner -print 2>/dev/null | sort | tail -n 1)"
  [ -n "$apksigner" ] && [ -x "$apksigner" ] || { echo 'apksigner não disponível para verificar o APK.' >&2; exit 4; }
  command -v jarsigner >/dev/null || { echo 'jarsigner não disponível para verificar o AAB.' >&2; exit 4; }
  for apk in "$artifact_dir"/*.apk; do [ -f "$apk" ] && "$apksigner" verify --verbose --print-certs "$apk"; done
  for aab in "$artifact_dir"/*.aab; do [ -f "$aab" ] && jarsigner -verify -certs "$aab"; done
fi

(cd "$artifact_dir" && sha256sum ./*.apk ./*.aab 2>/dev/null > SHA256SUMS || true)
printf 'Android: perfil=%s apps=%s apk=%s aab=%s\n' "$profile" "$expected_count" "$apk_count" "$aab_count"
