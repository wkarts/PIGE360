#!/usr/bin/env bash
set -euo pipefail

if [[ "${REMOTE_DEPLOY_ENABLED:-false}" != "true" ]]; then
  echo "REMOTE_DEPLOY_ENABLED não está habilitado; deploy recusado." >&2
  exit 78
fi
: "${SAAS_DEPLOY_HOST:?SAAS_DEPLOY_HOST ausente}"
: "${SAAS_DEPLOY_USER:?SAAS_DEPLOY_USER ausente}"
: "${SAAS_DEPLOY_PATH:?SAAS_DEPLOY_PATH ausente}"
port="${SAAS_DEPLOY_PORT:-22}"
image_mode="${SAAS_IMAGE_MODE:-source}"
deploy_target="${SAAS_DEPLOY_TARGET:-base}"
version="$(tr -d '[:space:]' < VERSION)"
[[ "$version" =~ ^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$ ]] || {
  echo "VERSION inválida para deploy remoto." >&2
  exit 2
}
[[ "$SAAS_DEPLOY_USER" =~ ^[A-Za-z0-9._-]+$ ]] || { echo 'SAAS_DEPLOY_USER inválido.' >&2; exit 2; }
[[ "$SAAS_DEPLOY_HOST" =~ ^[A-Za-z0-9.-]+$ ]] || { echo 'SAAS_DEPLOY_HOST inválido.' >&2; exit 2; }
[[ "$port" =~ ^[0-9]{1,5}$ ]] && (( port >= 1 && port <= 65535 )) || { echo 'SAAS_DEPLOY_PORT inválida.' >&2; exit 2; }
[[ "$image_mode" == source || "$image_mode" == registry ]] || { echo 'SAAS_IMAGE_MODE inválido.' >&2; exit 2; }
[[ "$deploy_target" =~ ^(base|cloudpanel|edge|dockge|portainer)$ ]] || { echo 'SAAS_DEPLOY_TARGET inválido.' >&2; exit 2; }
[[ "$SAAS_DEPLOY_PATH" =~ ^/[A-Za-z0-9._/-]+$ ]] \
  && [[ "$SAAS_DEPLOY_PATH" != / ]] \
  && [[ "$SAAS_DEPLOY_PATH" != *"/../"* ]] && [[ "$SAAS_DEPLOY_PATH" != */.. ]] \
  && [[ "$SAAS_DEPLOY_PATH" != *"/./"* ]] && [[ "$SAAS_DEPLOY_PATH" != */. ]] || {
  echo 'SAAS_DEPLOY_PATH deve ser absoluto e conter somente caracteres seguros.' >&2
  exit 2
}
bundle="${1:-release/output/PIGE360-${version}-self-hosted.zip}"
[[ -f "$bundle" ]] || { echo "Bundle self-hosted ausente: $bundle" >&2; exit 4; }
command -v ssh >/dev/null 2>&1 || exit 3
command -v scp >/dev/null 2>&1 || exit 3

remote_tmp="/tmp/PIGE360-${version}-self-hosted.zip"
scp -P "$port" -o BatchMode=yes -o StrictHostKeyChecking=yes "$bundle" "${SAAS_DEPLOY_USER}@${SAAS_DEPLOY_HOST}:${remote_tmp}"
ssh -p "$port" -o BatchMode=yes -o StrictHostKeyChecking=yes "${SAAS_DEPLOY_USER}@${SAAS_DEPLOY_HOST}" \
  "PIGE360_BUNDLE='${remote_tmp}' PIGE360_DEPLOY_PATH='${SAAS_DEPLOY_PATH}' PIGE360_IMAGE_MODE='${image_mode}' PIGE360_DEPLOY_TARGET='${deploy_target}' bash -s" <<'REMOTE'
set -euo pipefail
command -v docker >/dev/null 2>&1 || { echo 'Docker ausente no host.' >&2; exit 3; }
docker compose version >/dev/null 2>&1 || { echo 'Docker Compose v2 ausente no host.' >&2; exit 3; }
command -v unzip >/dev/null 2>&1 || { echo 'unzip ausente no host.' >&2; exit 3; }
mkdir -p "${PIGE360_DEPLOY_PATH}/releases"
release_dir="${PIGE360_DEPLOY_PATH}/releases/$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "$release_dir"
unzip -q "$PIGE360_BUNDLE" -d "$release_dir"
root="$(find "$release_dir" -maxdepth 2 -type f -name compose.yaml -printf '%h\n' | head -1)"
[[ -n "$root" ]] || { echo 'compose.yaml não encontrado no bundle.' >&2; exit 4; }
[[ -f "${PIGE360_DEPLOY_PATH}/.env" ]] || { echo '.env persistente ausente no diretório de deploy.' >&2; exit 5; }
[[ -d "${PIGE360_DEPLOY_PATH}/runtime-secrets" ]] || { echo 'runtime-secrets persistente ausente.' >&2; exit 5; }
export PIGE360_ENV_FILE="${PIGE360_DEPLOY_PATH}/.env"
export PIGE360_SECRETS_DIR="${PIGE360_DEPLOY_PATH}/runtime-secrets"
export PIGE360_STATE_DIR="${PIGE360_DEPLOY_PATH}/state"
export PIGE360_CURRENT_LINK="${PIGE360_DEPLOY_PATH}/current"

if [[ -L "${PIGE360_DEPLOY_PATH}/current" || -d "${PIGE360_DEPLOY_PATH}/current" ]]; then
  current_root="$(readlink -f "${PIGE360_DEPLOY_PATH}/current")"
  [[ -f "$current_root/VERSION" ]] || { echo 'Ponteiro current inválido.' >&2; exit 5; }
  PIGE360_CURRENT_ROOT="$current_root" sh "$root/deploy/self-hosted/update.sh" "$root"
else
  PIGE360_ROOT="$root" sh "$root/deploy/self-hosted/install.sh" \
    --mode "$PIGE360_IMAGE_MODE" --target "$PIGE360_DEPLOY_TARGET"
  ln -sfn "$root" "${PIGE360_DEPLOY_PATH}/current"
fi
rm -f "$PIGE360_BUNDLE"
REMOTE
