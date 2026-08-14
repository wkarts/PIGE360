#!/bin/sh
set -eu
target="${1:-}"
[ -n "$target" ] || { echo 'Informe o target Rust.' >&2; exit 2; }
command -v cargo >/dev/null || { echo 'SKIPPED_NOT_CONFIGURED: cargo não disponível.' >&2; exit 3; }
command -v npm >/dev/null || { echo 'SKIPPED_NOT_CONFIGURED: npm não disponível.' >&2; exit 3; }
version="$(tr -d '[:space:]' < VERSION)"
case "$version" in
  [0-9]*.[0-9]*.[0-9]*-alpha.[0-9]*) ;;
  *) echo "Versão alpha inválida para o empacotamento desktop: $version" >&2; exit 4 ;;
esac
desktop_tauri_config=''
if [ "${RUNNER_OS:-}" = "Windows" ]; then
  # O MSI aceita apenas um identificador de pré-release numérico. A versão
  # pública permanece em VERSION; o override vale somente para o empacotador.
  msi_version="${version%-alpha.*}-${version##*.}"
  desktop_tauri_config="{\"version\":\"$msi_version\"}"
  perl_binary="${PIGE360_STRAWBERRY_PERL:-}"
  [ -n "$perl_binary" ] || {
    echo 'PIGE360_STRAWBERRY_PERL não foi preparado para o OpenSSL no Windows.' >&2
    exit 3
  }
  case "$perl_binary" in
    [A-Za-z]:\\*)
      command -v cygpath >/dev/null || {
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
bash scripts/frontend/install-dependencies.sh
mkdir -p release/artifacts/desktop
for app in desktop-admin pos-app; do
  (
    cd "apps/$app"
    if [ -n "$desktop_tauri_config" ]; then
      npx --no-install tauri build --target "$target" --config "$desktop_tauri_config"
    else
      npx --no-install tauri build --target "$target"
    fi
  )
done
find apps -path '*/src-tauri/target/*/release/bundle/*' -type f -exec cp {} release/artifacts/desktop/ \;
