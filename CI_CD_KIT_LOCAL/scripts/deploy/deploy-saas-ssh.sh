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
version="$(tr -d '[:space:]' < VERSION)"
bundle="${1:-release/output/PIGE360-${version}-self-hosted.zip}"
[[ -f "$bundle" ]] || { echo "Bundle self-hosted ausente: $bundle" >&2; exit 4; }
command -v ssh >/dev/null 2>&1 || exit 3
command -v scp >/dev/null 2>&1 || exit 3

remote_tmp="/tmp/PIGE360-${version}-self-hosted.zip"
scp -P "$port" -o BatchMode=yes -o StrictHostKeyChecking=yes "$bundle" "${SAAS_DEPLOY_USER}@${SAAS_DEPLOY_HOST}:${remote_tmp}"
ssh -p "$port" -o BatchMode=yes -o StrictHostKeyChecking=yes "${SAAS_DEPLOY_USER}@${SAAS_DEPLOY_HOST}" \
  "PIGE360_BUNDLE='${remote_tmp}' PIGE360_DEPLOY_PATH='${SAAS_DEPLOY_PATH}' bash -s" <<'REMOTE'
set -euo pipefail
command -v docker >/dev/null 2>&1 || { echo 'Docker ausente no host.' >&2; exit 3; }
command -v unzip >/dev/null 2>&1 || { echo 'unzip ausente no host.' >&2; exit 3; }
mkdir -p "${PIGE360_DEPLOY_PATH}/releases"
release_dir="${PIGE360_DEPLOY_PATH}/releases/$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "$release_dir"
unzip -q "$PIGE360_BUNDLE" -d "$release_dir"
root="$(find "$release_dir" -maxdepth 2 -type f -name compose.yaml -printf '%h\n' | head -1)"
[[ -n "$root" ]] || { echo 'compose.yaml não encontrado no bundle.' >&2; exit 4; }
[[ -f "${PIGE360_DEPLOY_PATH}/.env" ]] || { echo '.env persistente ausente no diretório de deploy.' >&2; exit 5; }
[[ -d "${PIGE360_DEPLOY_PATH}/runtime-secrets" ]] || { echo 'runtime-secrets persistente ausente.' >&2; exit 5; }
ln -sfn "${PIGE360_DEPLOY_PATH}/.env" "$root/.env"
ln -sfn "${PIGE360_DEPLOY_PATH}/runtime-secrets" "$root/runtime-secrets"
cd "$root"
docker compose -f compose.yaml -f compose.production.yaml config >/dev/null
docker compose -f compose.yaml -f compose.production.yaml run --rm pige360-migrations
docker compose -f compose.yaml -f compose.production.yaml up -d --remove-orphans
curl_cmd=''; command -v curl >/dev/null 2>&1 && curl_cmd='curl -fsS http://127.0.0.1:8000/api/v1/health/ready'
[[ -z "$curl_cmd" ]] || sh -c "$curl_cmd" >/dev/null
ln -sfn "$root" "${PIGE360_DEPLOY_PATH}/current"
rm -f "$PIGE360_BUNDLE"
REMOTE
