#!/bin/sh
set -eu
out="${1:-backups/$(date -u +%Y%m%dT%H%M%SZ)}"
mkdir -p "$out"
command -v docker >/dev/null 2>&1 || { echo 'Docker indisponível.' >&2; exit 3; }
docker compose exec -T pige360-postgres-control pg_dump -U pige360_control -Fc platform_control > "$out/platform-control.dump"
docker compose exec -T pige360-minio sh -c 'echo Use mc mirror com credenciais por secret e bucket por tenant' > "$out/OBJECT-STORAGE-INSTRUCTIONS.txt"
sha256sum "$out"/* > "$out/SHA256SUMS"
echo "Backup criado em $out. Bancos de tenant devem ser exportados individualmente pelo catálogo do Control Plane."
