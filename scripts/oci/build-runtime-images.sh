#!/usr/bin/env bash
set -euo pipefail

root_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$root_dir"
. "$root_dir/scripts/oci/image-catalog.sh"

target="${1:-all}"
output_dir="${2:-release/artifacts/docker}"
image_tag="${PIGE360_IMAGE_TAG:-$(tr -d '[:space:]' < VERSION)}"

case "$target" in
  base|api|applications|all) ;;
  *)
    echo "Uso: $0 [base|api|applications|all] [diretório-de-saída]" >&2
    exit 2
    ;;
esac

command -v docker >/dev/null 2>&1 || {
  echo "Docker com Buildx é obrigatório para construir imagens executáveis." >&2
  exit 3
}
docker buildx version >/dev/null 2>&1 || {
  echo "Docker Buildx é obrigatório para construir imagens executáveis." >&2
  exit 3
}

# As imagens base são exportadas com --load, portanto ficam no Docker Engine
# local. O builder docker-container ativado por docker/setup-buildx-action não
# enxerga automaticamente essas tags e tenta buscá-las no Docker Hub. Forçamos
# o builder padrão (driver docker) para manter a cadeia base -> API -> workers
# inteiramente no Engine do runner, sem registro remoto.
engine_builder="default"
docker buildx inspect "$engine_builder" >/dev/null 2>&1 || {
  echo "O builder Docker Engine padrão '$engine_builder' não está disponível." >&2
  exit 3
}

mkdir -p "$output_dir"

build_image() {
  local name="$1"
  local dockerfile="$2"
  shift 2
  local image="${name}:${image_tag}"
  local safe_name="${name//\//-}"
  local metadata="$output_dir/${safe_name}.metadata.json"

  docker buildx build \
    --builder "$engine_builder" \
    --load \
    --provenance=false \
    --sbom=false \
    --metadata-file "$metadata" \
    --build-arg "VERSION=$image_tag" \
    -f "$dockerfile" \
    -t "$image" \
    "$@" \
    .

  docker image inspect "$image" > "$output_dir/${safe_name}.inspect.json"
  docker image save "$image" -o "$output_dir/${safe_name}.tar"
  sha256sum "$output_dir/${safe_name}.tar" > "$output_dir/${safe_name}.tar.sha256"
}

build_base() {
  build_image "pige360-base-python" "infra/docker/base/Dockerfile.python"
  build_image "pige360-base-node" "infra/docker/base/Dockerfile.node"
  build_image "pige360-base-runtime" "infra/docker/base/Dockerfile.runtime"
  build_image "pige360-base-rust-tauri" "infra/docker/base/Dockerfile.rust-tauri"
}

build_api() {
  build_image "pige360-api" "infra/docker/Dockerfile.api" \
    --build-arg "PYTHON_BASE_IMAGE=pige360-base-python:${image_tag}"
}

build_applications() {
  build_image "pige360-web" "infra/docker/Dockerfile.web" \
    --build-arg "NODE_BASE_IMAGE=pige360-base-node:${image_tag}" \
    --build-arg "IMAGE_NAME=pige360-web" \
    --build-arg "APP_DIR=apps/tenant-admin-web" \
    --build-arg "NPM_INSTALL_MODE=ci"
  build_image "pige360-platform-console" "infra/docker/Dockerfile.web" \
    --build-arg "NODE_BASE_IMAGE=pige360-base-node:${image_tag}" \
    --build-arg "IMAGE_NAME=pige360-platform-console" \
    --build-arg "APP_DIR=apps/platform-console" \
    --build-arg "NPM_INSTALL_MODE=ci"
  build_image "pige360-branding-studio" "infra/docker/Dockerfile.web" \
    --build-arg "NODE_BASE_IMAGE=pige360-base-node:${image_tag}" \
    --build-arg "IMAGE_NAME=pige360-branding-studio" \
    --build-arg "APP_DIR=apps/branding-studio" \
    --build-arg "NPM_INSTALL_MODE=ci"
  build_image "pige360-tenant-download-center" "infra/docker/Dockerfile.web" \
    --build-arg "NODE_BASE_IMAGE=pige360-base-node:${image_tag}" \
    --build-arg "IMAGE_NAME=pige360-tenant-download-center" \
    --build-arg "APP_DIR=apps/tenant-download-center" \
    --build-arg "NPM_INSTALL_MODE=ci"
  build_image "pige360-worker" "infra/docker/Dockerfile.worker" \
    --build-arg "API_IMAGE=pige360-api:${image_tag}"
  build_image "pige360-migrations" "infra/docker/Dockerfile.migrations" \
    --build-arg "API_IMAGE=pige360-api:${image_tag}"
  build_image "pige360-ops" "infra/docker/Dockerfile.ops" \
    --build-arg "API_IMAGE=pige360-api:${image_tag}"
  build_image "pige360-reporting" "infra/docker/Dockerfile.reporting" \
    --build-arg "API_IMAGE=pige360-api:${image_tag}"
}

case "$target" in
  base)
    expected_images=("${PIGE360_BASE_IMAGE_NAMES[@]}")
    build_base
    ;;
  api)
    expected_images=(pige360-api)
    build_api
    ;;
  applications)
    expected_images=("${PIGE360_APPLICATION_LAYER_IMAGE_NAMES[@]}")
    build_applications
    ;;
  all)
    expected_images=("${PIGE360_ALL_IMAGE_NAMES[@]}")
    build_base
    build_api
    build_applications
    ;;
esac

expected_csv="$(IFS=,; printf '%s' "${expected_images[*]}")"
python3 - "$output_dir" "$image_tag" "$target" "$expected_csv" <<'PY'
from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

output = Path(sys.argv[1])
records = []
for name in sys.argv[4].split(","):
    tar = output / f"{name}.tar"
    if not tar.is_file():
        raise SystemExit(f"Imagem exportada ausente: {tar}")
    records.append({
        "name": name,
        "archive": tar.name,
        "sha256": hashlib.sha256(tar.read_bytes()).hexdigest(),
        "bytes": tar.stat().st_size,
    })
(output / "images-manifest.json").write_text(json.dumps({
    "schema_version": 1,
    "image_tag": sys.argv[2],
    "target": sys.argv[3],
    "runtime_build_executed": True,
    "created_at": datetime.now(timezone.utc).isoformat(),
    "images": records,
}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
PY
