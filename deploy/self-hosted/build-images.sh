#!/bin/sh
set -eu

root="$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)"
PIGE360_ROOT="${PIGE360_ROOT:-$root}"
. "$root/deploy/self-hosted/lib.sh"
pige_prepare_context
pige_require_docker

push=false
if [ "${1:-}" = "--push" ]; then
  push=true
  [ "$PIGE360_IMAGE_MODE" = registry ] || pige_die "--push exige PIGE360_IMAGE_MODE=registry."
fi

cd "$PIGE360_ROOT"
version="$PIGE360_IMAGE_TAG"
pige_info "construindo imagens self-hosted ${version}"

docker build --pull --build-arg "VERSION=$version" \
  -f infra/docker/base/Dockerfile.python -t "pige360-base-python:$version" .
docker build --pull --build-arg "VERSION=$version" \
  -f infra/docker/base/Dockerfile.node -t "pige360-base-node:$version" .
docker build --build-arg "VERSION=$version" \
  --build-arg "PYTHON_BASE_IMAGE=pige360-base-python:$version" \
  -f infra/docker/Dockerfile.api -t "$PIGE360_API_IMAGE" .
docker build --build-arg "VERSION=$version" --build-arg "API_IMAGE=$PIGE360_API_IMAGE" \
  -f infra/docker/Dockerfile.migrations -t "$PIGE360_MIGRATIONS_IMAGE" .
docker build --build-arg "VERSION=$version" --build-arg "API_IMAGE=$PIGE360_API_IMAGE" \
  -f infra/docker/Dockerfile.worker -t "$PIGE360_WORKER_IMAGE" .

build_web() {
  app_dir="$1"
  image="$2"
  docker build --build-arg "VERSION=$version" \
    --build-arg "NODE_BASE_IMAGE=pige360-base-node:$version" \
    --build-arg "NPM_INSTALL_MODE=ci" --build-arg "APP_DIR=$app_dir" \
    -f infra/docker/Dockerfile.web -t "$image" .
}

build_web apps/tenant-admin-web "$PIGE360_WEB_IMAGE"
build_web apps/platform-console "$PIGE360_PLATFORM_CONSOLE_IMAGE"
build_web apps/branding-studio "$PIGE360_BRANDING_STUDIO_IMAGE"
build_web apps/tenant-download-center "$PIGE360_TENANT_DOWNLOAD_CENTER_IMAGE"

if [ "$push" = true ]; then
  for image in \
    "$PIGE360_API_IMAGE" "$PIGE360_MIGRATIONS_IMAGE" "$PIGE360_WORKER_IMAGE" \
    "$PIGE360_WEB_IMAGE" "$PIGE360_PLATFORM_CONSOLE_IMAGE" \
    "$PIGE360_BRANDING_STUDIO_IMAGE" "$PIGE360_TENANT_DOWNLOAD_CENTER_IMAGE"; do
    docker push "$image"
  done
fi

pige_info "imagens self-hosted concluídas"
