#!/bin/sh
set -eu

target="${1:-}"
[ -n "$target" ] || { echo 'Informe o target Rust.' >&2; exit 2; }

case "$target" in
  x86_64-pc-windows-msvc) platform_arch='windows-x64' ;;
  i686-pc-windows-msvc) platform_arch='windows-x86' ;;
  x86_64-unknown-linux-gnu) platform_arch='linux-x64' ;;
  aarch64-unknown-linux-gnu) platform_arch='linux-arm64' ;;
  x86_64-apple-darwin) platform_arch='macos-x64' ;;
  aarch64-apple-darwin) platform_arch='macos-arm64' ;;
  *) echo "Target desktop não suportado: $target" >&2; exit 2 ;;
esac

command -v cargo >/dev/null 2>&1 || { echo 'SKIPPED_NOT_CONFIGURED: cargo não disponível.' >&2; exit 3; }
command -v npm >/dev/null 2>&1 || { echo 'SKIPPED_NOT_CONFIGURED: npm não disponível.' >&2; exit 3; }
command -v tar >/dev/null 2>&1 || { echo 'SKIPPED_NOT_CONFIGURED: tar não disponível.' >&2; exit 3; }
if command -v sha256sum >/dev/null 2>&1; then
  checksum_write() { sha256sum "$@"; }
  checksum_check() { sha256sum --check "$1"; }
elif command -v shasum >/dev/null 2>&1; then
  checksum_write() { shasum -a 256 "$@"; }
  checksum_check() { shasum -a 256 --check "$1"; }
else
  echo 'SKIPPED_NOT_CONFIGURED: sha256sum ou shasum é obrigatório.' >&2
  exit 3
fi

version="$(tr -d '[:space:]' < VERSION)"
prerelease_id='(0|[1-9][0-9]*|[0-9A-Za-z-]*[A-Za-z-][0-9A-Za-z-]*)'
semver_re="^(0|[1-9][0-9]*)\\.(0|[1-9][0-9]*)\\.(0|[1-9][0-9]*)(-${prerelease_id}(\\.${prerelease_id})*)?(\\+[0-9A-Za-z-]+(\\.[0-9A-Za-z-]+)*)?$"
printf '%s\n' "$version" | grep -Eq "$semver_re" || {
  echo "Versão SemVer inválida para o empacotamento desktop: $version" >&2
  exit 4
}

desktop_tauri_config=''
if [ "${RUNNER_OS:-}" = "Windows" ]; then
  # WiX/MSI aceita apenas a parte numérica. VERSION e os manifests de release
  # continuam registrando o SemVer completo, inclusive eventual prerelease.
  msi_version="${version%%[-+]*}"
  desktop_tauri_config="{\"version\":\"$msi_version\"}"
  perl_binary="${PIGE360_STRAWBERRY_PERL:-}"
  [ -n "$perl_binary" ] || {
    echo 'PIGE360_STRAWBERRY_PERL não foi preparado para o OpenSSL no Windows.' >&2
    exit 3
  }
  case "$perl_binary" in
    [A-Za-z]:\\*)
      command -v cygpath >/dev/null 2>&1 || {
        echo 'cygpath é obrigatório para expor o Strawberry Perl ao Git Bash.' >&2
        exit 3
      }
      perl_binary="$(cygpath -u "$perl_binary")"
      ;;
  esac
  [ -x "$perl_binary" ] || {
    echo "Strawberry Perl inválido: $perl_binary" >&2
    exit 3
  }
  export PATH="$(dirname "$perl_binary"):$PATH"
  perl -MLocale::Maketext::Simple -e 1
fi

root_dir="$(pwd)"
output_dir="$root_dir/release/artifacts/desktop/$platform_arch"
rm -rf "$output_dir"
mkdir -p "$output_dir"
bash scripts/frontend/install-dependencies.sh

ensure_lockfile() {
  manifest="$1"
  lockfile="$(dirname "$manifest")/Cargo.lock"
  if [ ! -f "$lockfile" ]; then
    if [ "${PIGE360_REQUIRE_LOCKED:-false}" = 'true' ]; then
      echo "Cargo.lock obrigatório e ausente: $lockfile" >&2
      exit 4
    fi
    cargo generate-lockfile --manifest-path "$manifest"
  fi
  cargo metadata --manifest-path "$manifest" --locked --format-version 1 >/dev/null
}

artifact_count=0
for app in desktop-admin pos-app; do
  app_dir="$root_dir/apps/$app"
  manifest="$app_dir/src-tauri/Cargo.toml"
  ensure_lockfile "$manifest"

  if [ -n "${PIGE360_CARGO_TARGET_ROOT:-}" ]; then
    cargo_target_dir="${PIGE360_CARGO_TARGET_ROOT%/}/$app"
  elif [ "${RUNNER_OS:-}" = 'Windows' ]; then
    # Caminho curto e previsível para evitar MAX_PATH/LNK1104 no runner.
    cargo_target_dir="C:/pige360-target/${GITHUB_RUN_ID:-local}/$app"
  else
    cargo_target_dir="$app_dir/src-tauri/target"
  fi

  (
    cd "$app_dir"
    export CARGO_TARGET_DIR="$cargo_target_dir"
    if [ -n "$desktop_tauri_config" ]; then
      npx --no-install tauri build --target "$target" --config "$desktop_tauri_config"
    else
      npx --no-install tauri build --target "$target"
    fi
  )

  bundle="$cargo_target_dir/$target/release/bundle"
  [ -d "$bundle" ] || {
    echo "Bundle desktop final não encontrado: $bundle" >&2
    exit 4
  }
  archive="$output_dir/PIGE360-v${version}-${app}-${platform_arch}.tar.gz"
  tar -C "$bundle" -czf "$archive" .
  [ -s "$archive" ] || { echo "Bundle desktop vazio: $archive" >&2; exit 4; }
  artifact_count=$((artifact_count + 1))
done

[ "$artifact_count" -eq 2 ] || {
  echo "Esperados 2 bundles desktop finais; encontrados $artifact_count." >&2
  exit 4
}
(
  cd "$output_dir"
  checksum_write ./*.tar.gz > SHA256SUMS
  checksum_check SHA256SUMS
)
printf 'Desktop: versão=%s alvo=%s bundles=%s\n' "$version" "$target" "$artifact_count"
