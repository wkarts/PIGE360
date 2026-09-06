#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
DOCKER_IMAGE="${DOCKER_IMAGE:-pige360-deployer-cloudpanel-builder:debian12}"
TARGET_ARGS=("${@:---all}")

# Corrige caso ${@:---all} vire um único argumento vazio.
if [[ $# -eq 0 ]]; then
  TARGET_ARGS=("--all")
fi

cat > "$ROOT_DIR/Dockerfile.cloudpanel-builder" <<'DOCKERFILE'
FROM rust:1-bookworm

ENV DEBIAN_FRONTEND=noninteractive

WORKDIR /workspace

COPY scripts/linux/install-cloudpanel-build-deps.sh /tmp/install-cloudpanel-build-deps.sh
RUN chmod +x /tmp/install-cloudpanel-build-deps.sh \
  && /tmp/install-cloudpanel-build-deps.sh --all \
  && curl -fsSL https://deb.nodesource.com/setup_24.x | bash - \
  && apt-get install -y --no-install-recommends nodejs \
  && npm install -g npm@latest \
  && rm -rf /var/lib/apt/lists/*
DOCKERFILE

docker build -f "$ROOT_DIR/Dockerfile.cloudpanel-builder" -t "$DOCKER_IMAGE" "$ROOT_DIR"

docker run --rm \
  -v "$ROOT_DIR:/workspace" \
  -w /workspace \
  "$DOCKER_IMAGE" \
  bash ./scripts/linux/build-cloudpanel-release.sh "${TARGET_ARGS[@]}"
