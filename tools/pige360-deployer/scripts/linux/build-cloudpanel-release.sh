#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
VERSION="$(cat "$ROOT_DIR/VERSION" 2>/dev/null || echo "1.2.0")"
APP_ID="pige360-deployer"
CRATE_NAME="pige360_deployer"
FEATURES="${FEATURES:-mysql-db,postgres-db}"
BUILD_WEB="${BUILD_WEB:-true}"
BUILD_MODE="${BUILD_MODE:-release}"
OUTPUT_DIR="$ROOT_DIR/release/cloudpanel"

TARGETS=()

usage() {
  cat <<USAGE
Uso:
  scripts/linux/build-cloudpanel-release.sh --x64
  scripts/linux/build-cloudpanel-release.sh --x86
  scripts/linux/build-cloudpanel-release.sh --all

Variáveis opcionais:
  FEATURES=mysql-db,postgres-db   Recursos Cargo habilitados no binário.
  BUILD_WEB=true|false            Rebuild do frontend antes de empacotar.
  BUILD_MODE=release              Modo Cargo.

Observação:
  x64 = x86_64-unknown-linux-gnu
  x86 = i686-unknown-linux-gnu

Para preparar Debian/Ubuntu:
  bash scripts/linux/install-cloudpanel-build-deps.sh --all
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --x64|--amd64)
      TARGETS+=("x86_64-unknown-linux-gnu:x64")
      ;;
    --x86|--i686|--32)
      TARGETS+=("i686-unknown-linux-gnu:x86")
      ;;
    --all)
      TARGETS+=("x86_64-unknown-linux-gnu:x64" "i686-unknown-linux-gnu:x86")
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

if [[ ${#TARGETS[@]} -eq 0 ]]; then
  TARGETS+=("x86_64-unknown-linux-gnu:x64")
fi

command -v cargo >/dev/null 2>&1 || {
  echo "Cargo/Rust não encontrado. Instale Rust antes de compilar."
  exit 1
}
command -v npm >/dev/null 2>&1 || {
  echo "Node/npm não encontrado. Instale Node.js antes de compilar o frontend."
  exit 1
}

cd "$ROOT_DIR"
mkdir -p "$OUTPUT_DIR"

if [[ "$BUILD_WEB" == "true" ]]; then
  [[ -f package-lock.json ]] || {
    echo "package-lock.json é obrigatório para build reprodutível." >&2
    exit 1
  }
  npm ci
  npm run build:web
  node ./scripts/prepare-tauri-resources.mjs
fi

if [[ ! -f "$ROOT_DIR/dist/index.html" ]]; then
  echo "dist/index.html não encontrado. Execute npm run build:web."
  exit 1
fi

if command -v rustup >/dev/null 2>&1; then
  for item in "${TARGETS[@]}"; do
    triple="${item%%:*}"
    rustup target add "$triple" || true
  done
fi

for item in "${TARGETS[@]}"; do
  triple="${item%%:*}"
  label="${item##*:}"
  package_name="${APP_ID}-cloudpanel-v${VERSION}-linux-${label}"
  stage_dir="$OUTPUT_DIR/$package_name"
  archive="$OUTPUT_DIR/${package_name}.tar.gz"

  echo "============================================================"
  echo "Build Linux $label ($triple)"
  echo "============================================================"

  cargo_env=()
  if [[ "$triple" == "i686-unknown-linux-gnu" ]]; then
    # Cross-build headless x86 em host x64 Debian/Ubuntu.
    # Não habilita a feature desktop e, portanto, não depende de GTK/WebKit.
    # Requer toolchain multilib e OpenSSL i386 instalados pelo script de dependências.
    cargo_env+=("PKG_CONFIG_ALLOW_CROSS=1")
    cargo_env+=("PKG_CONFIG_LIBDIR=/usr/lib/i386-linux-gnu/pkgconfig:/usr/share/pkgconfig")
    cargo_env+=("PKG_CONFIG_PATH=/usr/lib/i386-linux-gnu/pkgconfig:/usr/share/pkgconfig")
    cargo_env+=("CARGO_TARGET_I686_UNKNOWN_LINUX_GNU_LINKER=gcc")
    cargo_env+=("CARGO_TARGET_I686_UNKNOWN_LINUX_GNU_RUSTFLAGS=-C link-arg=-m32")
    cargo_env+=("CFLAGS_i686_unknown_linux_gnu=-m32")
    cargo_env+=("CXXFLAGS_i686_unknown_linux_gnu=-m32")

    if ! env "${cargo_env[@]}" pkg-config --exists openssl; then
      echo "Dependências i386 do OpenSSL não encontradas para build x86 headless."
      echo "Execute: bash scripts/linux/install-cloudpanel-build-deps.sh --x86"
      exit 1
    fi
  fi

  headless_packages="$(
    env "${cargo_env[@]}" cargo tree \
      --manifest-path "$ROOT_DIR/src-tauri/Cargo.toml" \
      --target "$triple" \
      --locked \
      --no-default-features \
      --features "$FEATURES" \
      --edges normal,build \
      --prefix none \
      --format '{p}' \
      | awk '{print $1}' \
      | sort -u
  )"

  forbidden_headless_crates=(
    tauri
    tauri-build
    tauri-runtime
    tauri-runtime-wry
    wry
    gtk
    gtk-sys
    gdk
    gdk-sys
    webkit2gtk
    webkit2gtk-sys
    tray-icon
    muda
    libappindicator
    libappindicator-sys
  )
  unexpected_headless_crates=()
  for crate_name in "${forbidden_headless_crates[@]}"; do
    if grep -Fxq "$crate_name" <<<"$headless_packages"; then
      unexpected_headless_crates+=("$crate_name")
    fi
  done

  if [[ ${#unexpected_headless_crates[@]} -gt 0 ]]; then
    echo "O grafo CloudPanel headless contém crates gráficas/Tauri indevidas:" >&2
    printf '  - %s\n' "${unexpected_headless_crates[@]}" >&2
    echo "Mantenha tauri opcional e habilitado somente pelas features desktop ou mobile." >&2
    exit 1
  fi
  echo "Grafo headless validado: sem Tauri, GTK, GDK ou WebKitGTK."

  env "${cargo_env[@]}" cargo build \
    --manifest-path "$ROOT_DIR/src-tauri/Cargo.toml" \
    --target "$triple" \
    --locked \
    --no-default-features \
    --release \
    --features "$FEATURES"

  bin_path="$ROOT_DIR/src-tauri/target/$triple/release/$CRATE_NAME"
  if [[ ! -x "$bin_path" ]]; then
    echo "Binário não encontrado: $bin_path"
    exit 1
  fi

  rm -rf "$stage_dir"
  mkdir -p "$stage_dir/bin" "$stage_dir/dist" "$stage_dir/data" "$stage_dir/logs"

  cp "$bin_path" "$stage_dir/bin/$CRATE_NAME"
  chmod +x "$stage_dir/bin/$CRATE_NAME"

  cp -a "$ROOT_DIR/dist/." "$stage_dir/dist/"
  cp -a "$ROOT_DIR/deploy/cloudpanel/." "$stage_dir/"
  cp "$ROOT_DIR/deploy/cloudpanel/.env.example" "$stage_dir/.env"

  chmod +x "$stage_dir"/*.sh
  chmod +x "$stage_dir/bin/$CRATE_NAME"

  cat > "$stage_dir/RELEASE-MANIFEST.txt" <<MANIFEST
PIGE360 Deployer CloudPanel Release
Versão: $VERSION
Arquitetura: linux-$label
Target Rust: $triple
Binário: bin/$CRATE_NAME
Frontend: dist/index.html
Recursos Cargo: $FEATURES
Data de build: $(date -Is)

Execução CloudPanel:
  npm start

Execução terminal:
  ./start.sh
  ./status.sh
  ./logs.sh
  ./ports.sh

Portas configuráveis via .env:
  API:       PIGE360_DEPLOYER_API_HOST / PIGE360_DEPLOYER_API_PORT      (padrão 127.0.0.1:61001)
  WebPort:   PIGE360_DEPLOYER_WEB_HOST / PIGE360_DEPLOYER_WEB_PORT      (padrão 127.0.0.1:61002 ou PORT do CloudPanel)
  Webhook:   PIGE360_DEPLOYER_WEBHOOK_HOST / PIGE360_DEPLOYER_WEBHOOK_PORT (padrão 127.0.0.1:61003)
  WebSocket: PIGE360_DEPLOYER_WEBSOCKET_HOST / PIGE360_DEPLOYER_WEBSOCKET_PORT (padrão 127.0.0.1:61004)

Para publicar todas as portas:
  cp .env.public.example .env
MANIFEST

  tar -C "$OUTPUT_DIR" -czf "$archive" "$package_name"
  sha256sum "$archive" > "$archive.sha256"
  echo "Gerado: $archive"
  echo "SHA256: $archive.sha256"
done
