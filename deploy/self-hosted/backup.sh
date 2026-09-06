#!/bin/sh
set -eu

root="$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)"
PIGE360_ROOT="${PIGE360_ROOT:-$root}"
. "$root/deploy/self-hosted/lib.sh"
pige_prepare_context
pige_acquire_operation_lock
trap pige_release_operation_lock EXIT
pige_require_docker
command -v python3 >/dev/null 2>&1 || pige_die "python3 é obrigatório para validar o manifesto."

out="${1:-$PIGE360_ROOT/backups/$(date -u +%Y%m%dT%H%M%SZ)}"
out="$(pige_abspath "$out")"
[ ! -e "$out" ] || pige_die "destino de backup já existe: $out"
mkdir -p "$(dirname -- "$out")"
stage="${out}.partial.$$"
mkdir -m 0700 -p "$stage/tenant-databases" "$stage/objects"
umask 077

tab="$(printf '\t')"
catalog_sql="SELECT id,code,status,database_name,database_user,bucket_name FROM platform_tenants WHERE status IN ('active','degraded','suspended') ORDER BY id"
pige_compose exec -T pige360-postgres-control \
  psql -X -U pige360_control -d platform_control -v ON_ERROR_STOP=1 -A -t -F "$tab" -c "$catalog_sql" \
  > "$stage/tenants.tsv"
python3 "$PIGE360_ROOT/scripts/backup/backup_manifest.py" validate-catalog "$stage" >/dev/null

pige_info "exportando Control Plane"
pige_compose exec -T pige360-postgres-control \
  pg_dump -U pige360_control --format=custom --no-owner --no-privileges platform_control \
  > "$stage/platform-control.dump"
pige_compose exec -T pige360-postgres-control pg_restore --list \
  < "$stage/platform-control.dump" >/dev/null
{
  printf 'control='
  pige_compose exec -T pige360-postgres-control pg_dump --version
  printf 'tenants='
  pige_compose exec -T pige360-postgres-tenants pg_dump --version
} > "$stage/postgres-versions.txt"

pige_info "exportando bancos dedicados de tenants"
while IFS="$tab" read -r tenant_id code status database_name database_user bucket_name; do
  [ -n "$tenant_id" ] || continue
  pige_compose exec -T pige360-postgres-tenants \
    pg_dump -U pige360_tenant_admin --format=custom --no-owner --no-privileges "$database_name" \
    > "$stage/tenant-databases/${database_name}.dump"
  pige_compose exec -T pige360-postgres-tenants pg_restore --list \
    < "$stage/tenant-databases/${database_name}.dump" >/dev/null
done < "$stage/tenants.tsv"

pige_info "arquivando o volume persistente de arquivos locais dos tenants"
pige_compose run --rm --no-deps --no-build --user 0:0 -v "$stage:/backup" \
  --entrypoint python pige360-app-init -c '
from pathlib import Path
import tarfile

source = Path("/var/lib/pige360/tenants")
for item in source.rglob("*"):
    if item.is_symlink():
        raise SystemExit(f"link simbólico recusado no tenant storage: {item.relative_to(source)}")
with tarfile.open("/backup/tenant-storage.tar.gz", "w:gz") as archive:
    for item in sorted(source.iterdir()) if source.exists() else ():
        archive.add(item, arcname=item.name, recursive=True)
'

{
  printf '%s\n' pige360-platform
  cut -f6 "$stage/tenants.tsv"
} | sed '/^$/d' | LC_ALL=C sort -u > "$stage/buckets.txt"

pige_info "espelhando objetos atuais de cada bucket MinIO"
pige_compose run --rm --no-deps -v "$stage:/backup" --entrypoint /bin/sh pige360-minio-init -ec '
  access="$(cat "$MINIO_ACCESS_KEY_FILE")"
  secret="$(cat "$MINIO_SECRET_KEY_FILE")"
  mc alias set snapshot "$MINIO_ENDPOINT" "$access" "$secret" >/dev/null
  while IFS= read -r bucket; do
    [ -n "$bucket" ] || continue
    mkdir -p "/backup/objects/$bucket"
    mc stat "snapshot/$bucket" >/dev/null
    mc mirror --preserve "snapshot/$bucket" "/backup/objects/$bucket"
  done < /backup/buckets.txt
'

catalog_after="$stage/tenants-after.tsv"
pige_compose exec -T pige360-postgres-control \
  psql -X -U pige360_control -d platform_control -v ON_ERROR_STOP=1 -A -t -F "$tab" -c "$catalog_sql" \
  > "$catalog_after"
if ! cmp -s "$stage/tenants.tsv" "$catalog_after"; then
  pige_die "catálogo de tenants mudou durante o backup; snapshot parcial preservado para diagnóstico."
fi
rm -f "$catalog_after"

database_key_fingerprint="$(python3 -c 'import hashlib,sys; print(hashlib.sha256(open(sys.argv[1], "rb").read()).hexdigest())' "$PIGE360_SECRETS_DIR/database_secret_key.txt")"
python3 "$PIGE360_ROOT/scripts/backup/backup_manifest.py" create "$stage" \
  --version "$APP_VERSION" --target "$PIGE360_DEPLOY_TARGET" --image-mode "$PIGE360_IMAGE_MODE" \
  --database-key-fingerprint "$database_key_fingerprint" >/dev/null
python3 "$PIGE360_ROOT/scripts/backup/backup_manifest.py" verify "$stage" >/dev/null
mv "$stage" "$out"
pige_info "backup verificável concluído em $out"
pige_info "consistência: snapshot online por recurso; para corte global, pare escritas antes da execução"
