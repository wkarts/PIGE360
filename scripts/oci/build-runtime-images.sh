#!/usr/bin/env bash
set -euo pipefail

root_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$root_dir"

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

build_web_image() {
  local image_name="$1"
  local app_dir="$2"
  build_image "$image_name" "infra/docker/Dockerfile.web" \
    --build-arg "NODE_BASE_IMAGE=pige360-base-node:${image_tag}" \
    --build-arg "NPM_INSTALL_MODE=ci" \
    --build-arg "APP_DIR=${app_dir}"
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
  build_web_image "pige360-web" "apps/tenant-admin-web"
  build_web_image "pige360-platform-console" "apps/platform-console"
  build_web_image "pige360-branding-studio" "apps/branding-studio"
  build_web_image "pige360-tenant-download-center" "apps/tenant-download-center"
  build_image "pige360-worker" "infra/docker/Dockerfile.worker" \
    --build-arg "API_IMAGE=pige360-api:${image_tag}"
  build_image "pige360-migrations" "infra/docker/Dockerfile.migrations" \
    --build-arg "API_IMAGE=pige360-api:${image_tag}"
  build_image "pige360-reporting" "infra/docker/Dockerfile.reporting" \
    --build-arg "API_IMAGE=pige360-api:${image_tag}"
}

case "$target" in
  base)
    build_base
    ;;
  api)
    build_api
    ;;
  applications)
    build_applications
    ;;
  all)
    build_base
    build_api
    build_applications
    ;;
esac

python3 - "$output_dir" "$image_tag" "$target" <<'PY'
from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

output = Path(sys.argv[1])
records = []
for tar in sorted(output.glob("*.tar")):
    records.append({
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
