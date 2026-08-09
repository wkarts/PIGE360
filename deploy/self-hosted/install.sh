#!/bin/sh
set -eu
root="$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)"
cd "$root"
command -v docker >/dev/null 2>&1 || { echo 'Docker Engine/Compose v2 é obrigatório.' >&2; exit 3; }
[ -f .env ] || cp .env.example .env
[ -d runtime-secrets ] || bash scripts/local/init-secrets.sh runtime-secrets
docker compose -f compose.yaml -f compose.production.yaml config >/dev/null
echo 'Configuração validada. Revise .env e runtime-secrets antes de iniciar.'
echo 'Para iniciar: docker compose -f compose.yaml -f compose.production.yaml up -d'
