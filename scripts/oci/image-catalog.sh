#!/usr/bin/env bash

# Catálogo canônico das imagens first-party construídas pelos pipelines OCI.
# Os scripts de build e publicação carregam este arquivo para impedir que uma
# imagem exigida pelo deployment deixe de ser publicada por divergência entre
# listas independentes.

declare -ar PIGE360_BASE_IMAGE_NAMES=(
  pige360-base-python
  pige360-base-node
  pige360-base-runtime
  pige360-base-rust-tauri
)

declare -ar PIGE360_APPLICATION_LAYER_IMAGE_NAMES=(
  pige360-web
  pige360-platform-console
  pige360-branding-studio
  pige360-tenant-download-center
  pige360-worker
  pige360-migrations
  pige360-ops
  pige360-reporting
)

declare -ar PIGE360_RUNTIME_IMAGE_NAMES=(
  pige360-api
  "${PIGE360_APPLICATION_LAYER_IMAGE_NAMES[@]}"
)

declare -ar PIGE360_DEPLOY_IMAGE_NAMES=(
  pige360-api
  pige360-ops
  pige360-worker
  pige360-web
  pige360-platform-console
  pige360-branding-studio
  pige360-tenant-download-center
)

declare -ar PIGE360_ALL_IMAGE_NAMES=(
  "${PIGE360_BASE_IMAGE_NAMES[@]}"
  "${PIGE360_RUNTIME_IMAGE_NAMES[@]}"
)
