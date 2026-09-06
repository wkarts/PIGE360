#!/usr/bin/env bash
set -Eeuo pipefail

root_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$root_dir"
. "$root_dir/scripts/oci/image-catalog.sh"

deployment_environment="${1:-}"
image_tag="${2:-}"
artifact_dir="${3:-release/artifacts/docker/registry-smoke}"

case "$deployment_environment" in
  develop)
    [[ "$image_tag" =~ ^develop-[0-9a-f]{12}$ ]] || {
      echo "Smoke de develop exige a tag imutável develop-<sha12>: ${image_tag:-<vazia>}" >&2
      exit 2
    }
    ;;
  production)
    semver_re='^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)(-[0-9A-Za-z-]+(\.[0-9A-Za-z-]+)*)?$'
    [[ "$image_tag" =~ $semver_re ]] || {
      echo "Smoke de produção exige uma tag SemVer imutável: ${image_tag:-<vazia>}" >&2
      exit 2
    }
    ;;
  *)
    echo "Uso: $0 develop|production <tag-imutável> [diretório-de-evidências]" >&2
    exit 2
    ;;
esac

command -v docker >/dev/null 2>&1 || {
  echo "Docker é obrigatório para validar as imagens publicadas." >&2
  exit 3
}
docker compose version >/dev/null 2>&1 || {
  echo "Docker Compose v2 é obrigatório para validar as imagens publicadas." >&2
  exit 3
}
command -v curl >/dev/null 2>&1 || {
  echo "curl é obrigatório para validar o gateway publicado." >&2
  exit 3
}
command -v python3 >/dev/null 2>&1 || {
  echo "Python 3 é obrigatório para registrar as evidências do smoke." >&2
  exit 3
}

source_dir="$root_dir/deployments/$deployment_environment"
[[ -s "$source_dir/compose.yaml" && -s "$source_dir/.env.example" ]] || {
  echo "Deployment standalone incompleto em ${source_dir}." >&2
  exit 4
}

mkdir -p "$artifact_dir"
artifact_dir="$(cd "$artifact_dir" && pwd)"
work_dir="$(mktemp -d)"
project_suffix="${GITHUB_RUN_ID:-local}-${GITHUB_RUN_ATTEMPT:-1}-${RANDOM}"
project_name="pige360-registry-smoke-${deployment_environment}-${project_suffix}"
gateway_port="${PIGE360_REGISTRY_SMOKE_PORT:-58089}"
owner="${GITHUB_REPOSITORY_OWNER:-wkarts}"
registry="${PIGE360_GHCR_NAMESPACE:-ghcr.io/${owner}}"
registry="$(printf '%s' "$registry" | tr '[:upper:]' '[:lower:]')"
registry="${registry%/}"
current_stage="preparacao"
smoke_completed=false

cp -a "$source_dir/." "$work_dir/"
cp "$work_dir/.env.example" "$work_dir/.env"
chmod 600 "$work_dir/.env"

set_env_value() {
  local key="$1" value="$2" temporary="$work_dir/.env.tmp"
  awk -F= -v key="$key" -v value="$value" '
    BEGIN { found=0 }
    $1 == key { print key "=" value; found=1; next }
    { print }
    END { if (!found) print key "=" value }
  ' "$work_dir/.env" > "$temporary"
  chmod 600 "$temporary"
  mv "$temporary" "$work_dir/.env"
}

set_env_value PIGE360_ENVIRONMENT "$deployment_environment"
set_env_value COMPOSE_PROJECT_NAME "$project_name"
set_env_value PIGE360_PROJECT_NAME "$project_name"
set_env_value PIGE360_IMAGE_REGISTRY "$registry"
set_env_value OCI_REGISTRY "$registry"
set_env_value PIGE360_IMAGE_TAG "$image_tag"
set_env_value PIGE360_PULL_POLICY always
set_env_value GATEWAY_BIND_HOST 127.0.0.1
set_env_value GATEWAY_PORT "$gateway_port"
set_env_value APP_DEBUG false
set_env_value APP_DEMO_MODE false
base_domain="smoke.pige360.local"
api_host="api.smoke.pige360.local"
console_host="console.smoke.pige360.local"
branding_host="branding.smoke.pige360.local"
downloads_host="downloads.smoke.pige360.local"
set_env_value PIGE360_BASE_DOMAIN "$base_domain"
set_env_value TENANT_DEFAULT_BASE_DOMAIN "$base_domain"
set_env_value PLATFORM_API_HOST "$api_host"
set_env_value PLATFORM_CONSOLE_HOST "$console_host"
set_env_value PLATFORM_BRANDING_HOST "$branding_host"
set_env_value PLATFORM_DOWNLOADS_HOST "$downloads_host"
set_env_value ALLOWED_PLATFORM_HOSTS "${console_host},${api_host},${branding_host},${downloads_host}"

compose=(
  docker compose
  --project-directory "$work_dir"
  --env-file "$work_dir/.env"
  -f "$work_dir/compose.yaml"
)

write_result() {
  local status="$1" exit_code="$2" stage="$3" teardown_status="$4"
  python3 - "$artifact_dir/registry-smoke-manifest.json" \
    "$status" "$exit_code" "$stage" "$teardown_status" \
    "$deployment_environment" "$image_tag" "$registry" "$project_name" <<'PY'
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

(
    destination,
    status,
    exit_code,
    stage,
    teardown_status,
    environment,
    image_tag,
    registry,
    project_name,
) = sys.argv[1:]

payload = {
    "schema_version": 1,
    "status": status,
    "exit_code": int(exit_code),
    "failed_stage": None if status == "passed" else stage,
    "teardown": teardown_status,
    "environment": environment,
    "registry": registry,
    "image_tag": image_tag,
    "immutable_reference": True,
    "runtime_executed": True,
    "project_name": project_name,
    "services_checked": [
        "pige360-gateway",
        "pige360-api",
        "pige360-web",
        "pige360-platform-console",
        "pige360-branding-studio",
        "pige360-tenant-download-center",
    ],
    "generated_at": datetime.now(timezone.utc).isoformat(),
}
Path(destination).write_text(
    json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
    encoding="utf-8",
)
PY
}

cleanup() {
  local exit_code=$? down_code=0 final_status=failed teardown_status=failed
  trap - EXIT
  set +e
  "${compose[@]}" ps --all > "$artifact_dir/compose-ps.txt" 2>&1
  "${compose[@]}" logs --no-color --timestamps > "$artifact_dir/compose.log" 2>&1
  "${compose[@]}" down --volumes --remove-orphans --timeout 30 \
    > "$artifact_dir/compose-down.log" 2>&1
  down_code=$?
  if [[ "$down_code" -eq 0 ]]; then
    teardown_status=passed
  elif [[ "$exit_code" -eq 0 ]]; then
    exit_code=20
    current_stage=teardown
  fi
  if [[ "$exit_code" -eq 0 && "$smoke_completed" == true ]]; then
    final_status=passed
  fi
  write_result "$final_status" "$exit_code" "$current_stage" "$teardown_status"
  rm -rf -- "$work_dir"
  if [[ "$final_status" == passed ]]; then
    echo "Smoke remoto aprovado e teardown concluído: ${artifact_dir}"
  else
    echo "Smoke remoto falhou na etapa '${current_stage}'; consulte ${artifact_dir}." >&2
  fi
  exit "$exit_code"
}
trap cleanup EXIT

current_stage="compose-config"
"${compose[@]}" config -q
"${compose[@]}" config --images | sort -u > "$artifact_dir/compose-images.txt"

# Além do smoke HTTP, confirma antes do pull que todos os serviços first-party
# implantáveis estão fixados na mesma referência imutável recém-publicada.
for image in "${PIGE360_DEPLOY_IMAGE_NAMES[@]}"; do
  expected_ref="${registry}/${image}:${image_tag}"
  grep -Fqx -- "$expected_ref" "$artifact_dir/compose-images.txt" || {
    echo "Deployment não referencia a imagem publicada: ${expected_ref}" >&2
    exit 5
  }
done

current_stage="registry-pull"
# O pull ocorre em runner limpo e cobre todo o perfil padrão, incluindo as
# dependências third-party. O `up --pull never` subsequente prova que a subida
# usa exatamente os artefatos já obtidos do registry.
"${compose[@]}" pull > "$artifact_dir/compose-pull.log" 2>&1

current_stage="compose-up"
"${compose[@]}" up -d --no-build --pull never --wait \
  --wait-timeout "${PIGE360_REGISTRY_SMOKE_TIMEOUT_SECONDS:-600}" \
  pige360-gateway pige360-branding-studio pige360-tenant-download-center \
  > "$artifact_dir/compose-up.log" 2>&1

"${compose[@]}" ps --status running --services | sort \
  > "$artifact_dir/running-services.txt"
for service in \
  pige360-gateway \
  pige360-api \
  pige360-web \
  pige360-platform-console \
  pige360-branding-studio \
  pige360-tenant-download-center; do
  grep -Fqx -- "$service" "$artifact_dir/running-services.txt" || {
    echo "Serviço obrigatório não está em execução: ${service}" >&2
    exit 6
  }
done

base_url="http://127.0.0.1:${gateway_port}"

curl_common=(
  --fail --silent --show-error --location
  --retry 12 --retry-all-errors --retry-delay 2
  --connect-timeout 5 --max-time 30
)

current_stage="gateway-health"
curl "${curl_common[@]}" -H "Host: ${console_host}" \
  "${base_url}/healthz" > "$artifact_dir/gateway-healthz.txt"

current_stage="api-readiness"
curl "${curl_common[@]}" -H "Host: ${api_host}" \
  "${base_url}/api/v1/health/ready" > "$artifact_dir/api-health-ready.json"

current_stage="frontend-web"
curl "${curl_common[@]}" -H "Host: tenant.${base_domain}" \
  "${base_url}/" > "$artifact_dir/web.html"

current_stage="frontend-console"
curl "${curl_common[@]}" -H "Host: ${console_host}" \
  "${base_url}/" > "$artifact_dir/platform-console.html"

current_stage="frontend-branding"
curl "${curl_common[@]}" -H "Host: ${branding_host}" \
  "${base_url}/" > "$artifact_dir/branding-studio.html"

current_stage="frontend-downloads"
curl "${curl_common[@]}" -H "Host: ${downloads_host}" \
  "${base_url}/" > "$artifact_dir/tenant-download-center.html"

for response in \
  gateway-healthz.txt \
  api-health-ready.json \
  web.html \
  platform-console.html \
  branding-studio.html \
  tenant-download-center.html; do
  test -s "$artifact_dir/$response" || {
    echo "Resposta vazia no smoke remoto: ${response}" >&2
    exit 7
  }
done

current_stage="concluido"
smoke_completed=true
