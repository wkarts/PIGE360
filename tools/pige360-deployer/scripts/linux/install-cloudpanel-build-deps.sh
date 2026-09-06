#!/usr/bin/env bash
set -euo pipefail

TARGET="all"

usage() {
  cat <<USAGE
Uso:
  scripts/linux/install-cloudpanel-build-deps.sh --x64
  scripts/linux/install-cloudpanel-build-deps.sh --x86
  scripts/linux/install-cloudpanel-build-deps.sh --all

Instala dependências de build Debian/Ubuntu para gerar release CloudPanel.
- x64: x86_64-unknown-linux-gnu
- x86: i686-unknown-linux-gnu, com multiarch i386
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --x64|--amd64)
      TARGET="x64"
      ;;
    --x86|--i686|--32)
      TARGET="x86"
      ;;
    --all)
      TARGET="all"
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Parâmetro inválido: $1"
      usage
      exit 1
      ;;
  esac
  shift
done

if ! command -v apt-get >/dev/null 2>&1; then
  echo "Este instalador foi feito para Debian/Ubuntu com apt-get."
  exit 1
fi

if [[ "${EUID:-$(id -u)}" -ne 0 ]]; then
  SUDO="sudo"
else
  SUDO=""
fi

if [[ "$TARGET" == "x86" || "$TARGET" == "all" ]]; then
  $SUDO dpkg --add-architecture i386
fi

$SUDO apt-get update

COMMON_PACKAGES=(
  build-essential
  ca-certificates
  curl
  wget
  file
  pkg-config
  libssl-dev
)

if [[ "$TARGET" == "x86" || "$TARGET" == "all" ]]; then
  COMMON_PACKAGES+=(
    gcc-multilib
    g++-multilib
    libc6-dev-i386
  )
fi

$SUDO apt-get install -y --no-install-recommends "${COMMON_PACKAGES[@]}"

if [[ "$TARGET" == "x86" || "$TARGET" == "all" ]]; then
  I386_PACKAGES=(
    libssl-dev:i386
  )

  echo "Instalando bibliotecas multiarch i386 para build linux-x86..."
  if ! $SUDO apt-get install -y --no-install-recommends "${I386_PACKAGES[@]}"; then
    cat <<'WARN'

[AVISO] Não foi possível instalar todas as dependências i386.
O build x64 continuará funcionando, mas o build x86 headless depende das
bibliotecas multiarch i386 do Debian/Ubuntu, principalmente libssl-dev:i386.

Alternativas:
  1. Usar Debian 12 ou Ubuntu 22.04/24.04 com repositórios i386 habilitados.
  2. Compilar x64 normalmente e gerar x86 em um runner i386 dedicado.
WARN
    exit 1
  fi
fi

if command -v rustup >/dev/null 2>&1; then
  rustup target add x86_64-unknown-linux-gnu || true
  if [[ "$TARGET" == "x86" || "$TARGET" == "all" ]]; then
    rustup target add i686-unknown-linux-gnu || true
  fi
fi

echo "Dependências Debian/Ubuntu instaladas para: $TARGET"
