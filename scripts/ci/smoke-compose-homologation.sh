#!/usr/bin/env bash
set -euo pipefail

root_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$root_dir"

output_dir="${1:-release/artifacts/docker/compose-smoke}"
image_tag="${PIGE360_IMAGE_TAG:-$(tr -d '[:space:]' < VERSION)}"
project_name="pige360-homologation-${GITHUB_RUN_ID:-local}-${RANDOM}"
secrets_dir="$(mktemp -d)"
mkdir -p "$output_dir"

command -v docker >/dev/null 2>&1 || {
  echo "Docker Compose é obrigatório para o smoke test de homologação." >&2
  exit 3
}
docker compose version >/dev/null 2>&1 || {
  echo "Docker Compose v2 é obrigatório para o smoke test de homologação." >&2
  exit 3
}

cleanup() {
  set +e
  docker compose -p "$project_name" -f compose.yaml -f infra/compose/compose.homologation-smoke.yaml logs --no-color > "$output_dir/compose-smoke.log" 2>&1
  docker compose -p "$project_name" -f compose.yaml -f infra/compose/compose.homologation-smoke.yaml down --volumes --remove-orphans > "$output_dir/compose-teardown.log" 2>&1
  rm -rf "$secrets_dir"
}
trap cleanup EXIT

write_secret() {
  local name="$1"
  local value="$2"
  printf '%s' "$value" > "$secrets_dir/${name}.txt"
}

# Segredos efêmeros de CI: nunca são impressos, versionados nem enviados como artefato.
write_secret app_jwt_secret "ci-only-jwt-secret-abcdefghijklmnopqrstuvwxyz-0123456789-ABCDEFGHIJKLMNOPQRSTUVWXYZ"
write_secret bootstrap_token "ci-only-bootstrap-token"
write_secret minio_access_key "pige360-ci"
write_secret minio_secret_key "pige360-ci-minio-secret"
write_secret postgres_control_password "pige360-ci-control-password"
write_secret postgres_tenant_password "pige360-ci-tenant-password"
write_secret grafana_admin_password "pige360-ci-grafana-password"
write_secret cloudflare_control_tunnel_token "ci-only-cloudflare-control-disabled"
write_secret cloudflare_tenant_tunnel_token "ci-only-cloudflare-tenant-disabled"
write_secret database_secret_key "MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY="
write_secret redis_password "pige360-ci-redis-password"
write_secret rabbitmq_password "pige360-ci-rabbitmq-password"
write_secret worker_context_signing_key "ci-only-worker-context-signing-key-abcdefghijklmnopqrstuvwxyz-0123456789"
write_secret build_farm_token "ci-only-build-farm-token-abcdefghijklmnopqrstuvwxyz-0123456789"

export PIGE360_IMAGE_TAG="$image_tag"
export PIGE360_SECRETS_DIR="$secrets_dir"
export WEB_BIND_HOST="127.0.0.1"
export WEB_PUBLISHED_PORT="58081"

for image in "pige360-migrations:${image_tag}" "pige360-api:${image_tag}" "pige360-web:${image_tag}"; do
  docker image inspect "$image" >/dev/null
done

docker compose -p "$project_name" -f compose.yaml -f infra/compose/compose.homologation-smoke.yaml config -q
docker compose -p "$project_name" -f compose.yaml -f infra/compose/compose.homologation-smoke.yaml up -d --no-build --wait --wait-timeout 240 pige360-web

curl --fail --silent --show-error --retry 12 --retry-delay 2 "http://127.0.0.1:${WEB_PUBLISHED_PORT}/healthz" > "$output_dir/web-healthz.txt"
docker compose -p "$project_name" -f compose.yaml -f infra/compose/compose.homologation-smoke.yaml exec -T pige360-api \
  python -c "import urllib.request; request=urllib.request.Request('http://127.0.0.1:8000/api/v1/health/live', headers={'Host': 'console.platform.local'}); print(urllib.request.urlopen(request, timeout=10).read().decode())" \
  > "$output_dir/api-health-live.json"

python3 - "$output_dir/compose-smoke-manifest.json" "$image_tag" <<'PY'
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

Path(sys.argv[1]).write_text(json.dumps({
    "schema_version": 1,
    "status": "passed",
    "image_tag": sys.argv[2],
    "runtime_executed": True,
    "services": ["pige360-app-init", "pige360-api", "pige360-web"],
    "generated_at": datetime.now(timezone.utc).isoformat(),
}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
PY
