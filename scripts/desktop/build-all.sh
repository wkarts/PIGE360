#!/bin/sh
set -eu
target="${1:-}"
[ -n "$target" ] || { echo 'Informe o target Rust.' >&2; exit 2; }
command -v cargo >/dev/null 2>&1 || { echo 'cargo não disponível.' >&2; exit 3; }
command -v npm >/dev/null 2>&1 || { echo 'npm não disponível.' >&2; exit 3; }

if [ "${RUNNER_OS:-}" = "Windows" ]; then
  perl_exe="${PIGE360_WINDOWS_PERL:-C:/Strawberry/perl/bin/perl.exe}"
  if [ ! -f "$perl_exe" ]; then
    command -v powershell.exe >/dev/null 2>&1 || {
      echo 'PowerShell não disponível para preparar Strawberry Perl.' >&2
      exit 3
    }
    echo 'Instalando Strawberry Perl para o build vendorizado do OpenSSL.'
    powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass \
      -Command "choco install strawberryperl -y --no-progress"
  fi
  [ -f "$perl_exe" ] || {
    echo "Strawberry Perl não encontrado em $perl_exe." >&2
    exit 3
  }
  export PERL="$perl_exe"
  "$PERL" -MLocale::Maketext::Simple -e "1;" || {
    echo 'Strawberry Perl não possui Locale::Maketext::Simple.' >&2
    exit 3
  }
  echo "Perl nativo selecionado para OpenSSL: $PERL"
fi

bash scripts/frontend/install-dependencies.sh
mkdir -p release/artifacts/desktop
rm -f release/artifacts/desktop/* 2>/dev/null || true

apps="${PIGE360_DESKTOP_APPS:-desktop-admin pos-app}"
for app in $apps; do
  [ -d "apps/$app/src-tauri" ] || {
    echo "Aplicação Tauri ausente: $app" >&2
    exit 4
  }
  echo "Compilando $app para $target"
  (cd "apps/$app" && npx --no-install tauri build --target "$target")

  bundle_dir="apps/$app/src-tauri/target/$target/release/bundle"
  found=0
  case "$target" in
    *windows*)
      files="$(find "$bundle_dir" -type f \( -name '*.exe' -o -name '*.msi' \) 2>/dev/null | sort)"
      ;;
    *linux*)
      files="$(find "$bundle_dir" -type f \( -name '*.deb' -o -name '*.rpm' -o -name '*.AppImage' \) 2>/dev/null | sort)"
      ;;
    *apple-darwin*)
      files="$(find "$bundle_dir" -type f -name '*.dmg' 2>/dev/null | sort)"
      ;;
    *)
      echo "Target desktop não suportado para coleta de bundle: $target" >&2
      exit 4
      ;;
  esac

  while IFS= read -r file; do
    [ -n "$file" ] || continue
    found=1
    cp "$file" "release/artifacts/desktop/${app}-${target}-$(basename "$file")"
  done <<EOF
$files
EOF

  [ "$found" -eq 1 ] || {
    echo "Nenhum instalador final gerado para $app / $target" >&2
    exit 5
  }
done

echo "Artefatos desktop finais:"
find release/artifacts/desktop -maxdepth 1 -type f -print | sort
