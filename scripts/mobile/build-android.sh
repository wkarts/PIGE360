#!/bin/sh
set -eu

usage() {
  cat <<'EOF'
Uso: scripts/mobile/build-android.sh [--app <nome|all>] [--profile <debug|release>] [--artifacts <apk|aab|both>] [--targets <aarch64,armv7,i686,x86_64|all>] [--verify-signature]

Por padrão a homologação gera somente arm64-v8a. Para evitar APKs universais
excessivos, cada ABI é compilada e publicada como arquivo separado.
EOF
}

apps='family-app teacher-app student-app admin-app pos-app kiosk-app timeclock-app'
selected_app='all'
profile='release'
artifacts='both'
target_spec="${PIGE360_ANDROID_TARGETS:-aarch64}"
verify_signature='false'
max_apk_bytes="${PIGE360_ANDROID_MAX_APK_BYTES:-134217728}"
max_aab_bytes="${PIGE360_ANDROID_MAX_AAB_BYTES:-268435456}"

while [ "$#" -gt 0 ]; do
  case "$1" in
    --app) selected_app="${2:?Informe o aplicativo após --app}"; shift 2 ;;
    --profile) profile="${2:?Informe o perfil após --profile}"; shift 2 ;;
    --artifacts) artifacts="${2:?Informe o tipo após --artifacts}"; shift 2 ;;
    --targets) target_spec="${2:?Informe as arquiteturas após --targets}"; shift 2 ;;
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
case "$max_apk_bytes" in ''|*[!0-9]*) echo 'PIGE360_ANDROID_MAX_APK_BYTES deve ser inteiro.' >&2; exit 2 ;; esac
case "$max_aab_bytes" in ''|*[!0-9]*) echo 'PIGE360_ANDROID_MAX_AAB_BYTES deve ser inteiro.' >&2; exit 2 ;; esac

normalize_targets() {
  raw="$(printf '%s' "$1" | tr ',' ' ')"
  [ -n "$raw" ] || { echo 'Informe ao menos uma arquitetura Android.' >&2; exit 2; }
  [ "$raw" != 'all' ] || raw='aarch64 armv7 i686 x86_64'
  normalized=''
  for target in $raw; do
    case "$target" in
      aarch64|armv7|i686|x86_64) ;;
      *) echo "Arquitetura Android inválida: $target" >&2; exit 2 ;;
    esac
    case " $normalized " in *" $target "*) ;; *) normalized="$normalized $target" ;; esac
  done
  printf '%s\n' "${normalized# }"
}

abi_for_target() {
  case "$1" in
    aarch64) printf '%s\n' arm64-v8a ;;
    armv7) printf '%s\n' armeabi-v7a ;;
    i686) printf '%s\n' x86 ;;
    x86_64) printf '%s\n' x86_64 ;;
    *) return 2 ;;
  esac
}

selected_targets="$(normalize_targets "$target_spec")"

command -v cargo >/dev/null || { echo 'SKIPPED_NOT_CONFIGURED: Rust ausente.' >&2; exit 3; }
[ -n "${ANDROID_HOME:-}" ] || { echo 'SKIPPED_NOT_CONFIGURED: ANDROID_HOME ausente.' >&2; exit 3; }
[ -n "${NDK_HOME:-}" ] || { echo 'SKIPPED_NOT_CONFIGURED: NDK_HOME ausente.' >&2; exit 3; }
[ -d "$NDK_HOME" ] || { echo "SKIPPED_NOT_CONFIGURED: NDK_HOME inválido: $NDK_HOME" >&2; exit 3; }
command -v unzip >/dev/null || { echo 'unzip é obrigatório para validar o APK.' >&2; exit 3; }

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

show_largest_entries() {
  archive="$1"
  unzip -l "$archive" | awk 'NR > 3 && $1 ~ /^[0-9]+$/ { print $1, $4 }' | sort -nr | head -n 15 >&2 || true
}

verify_apk_abi_and_size() {
  apk="$1"
  expected_abi="$2"
  bytes="$(wc -c < "$apk" | tr -d '[:space:]')"
  mib=$((bytes / 1024 / 1024))
  if [ "$bytes" -gt "$max_apk_bytes" ]; then
    echo "APK acima do limite: $apk (${mib} MiB; máximo $((max_apk_bytes / 1024 / 1024)) MiB)." >&2
    show_largest_entries "$apk"
    exit 4
  fi
  actual_abis="$(unzip -Z1 "$apk" | sed -n 's#^lib/\([^/]*\)/.*#\1#p' | sort -u)"
  [ "$actual_abis" = "$expected_abi" ] || {
    echo "APK não é exclusivo para $expected_abi: $apk contém [${actual_abis:-nenhuma ABI}]." >&2
    exit 4
  }
  printf 'APK validado: %s (%s MiB, ABI %s)\n' "$(basename "$apk")" "$mib" "$expected_abi"
}

verify_aab_size() {
  aab="$1"
  bytes="$(wc -c < "$aab" | tr -d '[:space:]')"
  mib=$((bytes / 1024 / 1024))
  if [ "$bytes" -gt "$max_aab_bytes" ]; then
    echo "AAB acima do limite: $aab (${mib} MiB; máximo $((max_aab_bytes / 1024 / 1024)) MiB)." >&2
    show_largest_entries "$aab"
    exit 4
  fi
  printf 'AAB validado: %s (%s MiB)\n' "$(basename "$aab")" "$mib"
}

copy_output() {
  app="$1"
  target="$2"
  extension="$3"
  abi="$(abi_for_target "$target")"
  output_root="apps/$app/src-tauri/gen/android/app/build/outputs"
  outputs="$(find "$output_root" -type f -name "*.$extension" -print | sort)"
  output_count="$(printf '%s\n' "$outputs" | sed '/^$/d' | wc -l | tr -d '[:space:]')"
  [ "$output_count" -eq 1 ] || {
    echo "Esperado um .$extension para $app/$target; encontrados $output_count." >&2
    printf '%s\n' "$outputs" >&2
    exit 4
  }
  output="$outputs"
  destination="$artifact_dir/${app}-${profile}-${abi}.${extension}"
  cp "$output" "$destination"
  if [ "$extension" = 'apk' ]; then
    verify_apk_abi_and_size "$destination" "$abi"
  else
    verify_aab_size "$destination"
  fi
}

build_artifact() {
  app="$1"
  target="$2"
  extension="$3"
  (
    cd "apps/$app"
    if [ "${CI:-false}" = 'true' ]; then rm -rf src-tauri/gen/android; fi
    if [ ! -d src-tauri/gen/android/app ]; then npx --no-install tauri android init --ci --skip-targets-install; fi
    [ -d src-tauri/gen/android/app ] || { echo "Falha ao gerar o projeto Android para $app." >&2; exit 4; }
    rm -rf src-tauri/gen/android/app/build/outputs
    if [ "$profile" = 'debug' ]; then
      npx --no-install tauri android build "--$extension" --debug --target "$target" --split-per-abi
    else
      npx --no-install tauri android build "--$extension" --target "$target" --split-per-abi
    fi
  )
  copy_output "$app" "$target" "$extension"
}

for app in $selected_apps; do
  for target in $selected_targets; do
    [ "$wants_apk" = 'false' ] || build_artifact "$app" "$target" apk
    [ "$wants_aab" = 'false' ] || build_artifact "$app" "$target" aab
  done
done

app_count="$(printf '%s\n' "$selected_apps" | wc -w | tr -d '[:space:]')"
target_count="$(printf '%s\n' "$selected_targets" | wc -w | tr -d '[:space:]')"
expected_count=$((app_count * target_count))
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
printf 'Android: perfil=%s apps=%s targets=%s apk=%s aab=%s\n' "$profile" "$app_count" "$target_count" "$apk_count" "$aab_count"
