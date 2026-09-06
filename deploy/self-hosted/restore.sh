#!/bin/sh
set -eu

root="$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)"
archive=""
confirmation=""

usage() {
  printf '%s\n' "Uso: $0 DIRETORIO_BACKUP --confirm RESTORE-PIGE360"
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --confirm) [ "$#" -ge 2 ] || { usage >&2; exit 2; }; confirmation="$2"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    -*) usage >&2; exit 2 ;;
    *) [ -z "$archive" ] || { usage >&2; exit 2; }; archive="$1"; shift ;;
  esac
done
[ -n "$archive" ] || { usage >&2; exit 2; }
[ "$confirmation" = RESTORE-PIGE360 ] || {
  printf '%s\n' 'Restauração recusada: confirme explicitamente com --confirm RESTORE-PIGE360.' >&2
  exit 78
}
command -v python3 >/dev/null 2>&1 || { printf '%s\n' 'python3 é obrigatório.' >&2; exit 3; }

case "$archive" in
  /*) ;;
  *) archive="$(pwd -P)/$archive" ;;
esac
python3 "$root/scripts/backup/backup_manifest.py" verify "$archive" >/dev/null

manifest_target="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1], encoding="utf-8"))["deployment_target"])' "$archive/manifest.json")"
manifest_mode="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1], encoding="utf-8"))["image_mode"])' "$archive/manifest.json")"
PIGE360_ROOT="${PIGE360_ROOT:-$root}"
PIGE360_DEPLOY_TARGET="${PIGE360_DEPLOY_TARGET:-$manifest_target}"
PIGE360_IMAGE_MODE="${PIGE360_IMAGE_MODE:-$manifest_mode}"
export PIGE360_ROOT PIGE360_DEPLOY_TARGET PIGE360_IMAGE_MODE
. "$root/deploy/self-hosted/lib.sh"
pige_prepare_context
expected_key_fingerprint="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1], encoding="utf-8"))["database_secret_key_sha256"])' "$archive/manifest.json")"
actual_key_fingerprint="$(python3 -c 'import hashlib,sys; print(hashlib.sha256(open(sys.argv[1], "rb").read()).hexdigest())' "$PIGE360_SECRETS_DIR/database_secret_key.txt")"
[ "$actual_key_fingerprint" = "$expected_key_fingerprint" ] || \
  pige_die "DATABASE_SECRET_KEY não corresponde ao backup; nenhuma operação destrutiva foi iniciada."
backup_postgres_major="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1], encoding="utf-8"))["postgres_major"])' "$archive/manifest.json")"
runtime_postgres_major="$(sed -n 's/^[[:space:]]*image:[[:space:]]*postgres:\([0-9][0-9]*\).*/\1/p' "$PIGE360_ROOT/compose.yaml" | head -1)"
[ -n "$runtime_postgres_major" ] && [ "$runtime_postgres_major" = "$backup_postgres_major" ] || \
  pige_die "major PostgreSQL do backup ($backup_postgres_major) difere do runtime (${runtime_postgres_major:-desconhecido}); nenhuma operação destrutiva foi iniciada."
pige_require_docker
pige_compose config >/dev/null
pige_acquire_operation_lock

restore_failed=true
restored_catalog=""
restore_notice() {
  pige_release_operation_lock
  [ -z "$restored_catalog" ] || rm -f "$restored_catalog"
  if [ "$restore_failed" = true ]; then
    printf '%s\n' 'ERRO: restauração não concluída; o stack não foi declarado saudável e pode estar apenas parcialmente ativo. Revise os logs antes de nova tentativa.' >&2
  fi
}
trap restore_notice EXIT
trap 'exit 130' HUP INT TERM

pige_info "integridade e fingerprint aprovados; interrompendo o stack antes da restauração"
pige_compose stop
pige_compose up -d --no-build --wait --wait-timeout "${PIGE360_STARTUP_TIMEOUT_SECONDS:-300}" \
  pige360-postgres-control pige360-postgres-tenants pige360-minio

pige_info "restaurando o banco do Control Plane"
pige_compose exec -T pige360-postgres-control psql -X -U pige360_control -d postgres -v ON_ERROR_STOP=1 \
  -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname='platform_control' AND pid <> pg_backend_pid()" >/dev/null
pige_compose exec -T pige360-postgres-control dropdb -U pige360_control --if-exists platform_control
pige_compose exec -T pige360-postgres-control createdb -U pige360_control -O pige360_control platform_control
pige_compose exec -T pige360-postgres-control \
  pg_restore -U pige360_control --exit-on-error --no-owner --no-privileges -d platform_control \
  < "$archive/platform-control.dump"

# Atualiza apenas o schema Control antes de ler o catálogo restaurado. As
# migrations tenant rodam somente depois que todos os dumps forem importados.
pige_compose run --rm --no-deps --no-build -w /opt/pige360 --entrypoint python pige360-app-init \
  -m alembic -c backend/alembic_control/alembic.ini upgrade head

tab="$(printf '\t')"
restored_catalog="$(mktemp "${TMPDIR:-/tmp}/pige360-restored-catalog.XXXXXX")"
catalog_sql="SELECT id,code,status,database_name,database_user,bucket_name FROM platform_tenants WHERE status IN ('active','degraded','suspended') ORDER BY id"
pige_compose exec -T pige360-postgres-control \
  psql -X -U pige360_control -d platform_control -v ON_ERROR_STOP=1 -A -t -F "$tab" -c "$catalog_sql" \
  > "$restored_catalog"
if ! cmp -s "$archive/tenants.tsv" "$restored_catalog"; then
  pige_die "catálogo restaurado diverge de tenants.tsv; nenhum banco de tenant foi alterado."
fi
rm -f "$restored_catalog"
restored_catalog=""
pige_compose run --rm --no-deps --no-build --entrypoint python pige360-app-init \
  -m app.shared.database.migrate_tenants --ensure-resources --skip-migrations

pige_info "restaurando bancos dedicados dos tenants"
while IFS="$tab" read -r tenant_id code status database_name database_user bucket_name; do
  [ -n "$tenant_id" ] || continue
  pige_compose exec -T pige360-postgres-tenants psql -X -U pige360_tenant_admin -d postgres -v ON_ERROR_STOP=1 \
    -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname='${database_name}' AND pid <> pg_backend_pid()" >/dev/null
  pige_compose exec -T pige360-postgres-tenants dropdb -U pige360_tenant_admin --if-exists "$database_name"
  pige_compose exec -T pige360-postgres-tenants createdb -U pige360_tenant_admin -O "$database_user" "$database_name"
  pige_compose exec -T pige360-postgres-tenants \
    pg_restore -U pige360_tenant_admin --role "$database_user" --exit-on-error --no-owner --no-privileges \
    -d "$database_name" < "$archive/tenant-databases/${database_name}.dump"
done < "$archive/tenants.tsv"

pige_info "restaurando o estado atual dos buckets MinIO"
pige_compose run --rm --no-deps -v "$archive:/backup:ro" --entrypoint /bin/sh pige360-minio-init -ec '
  access="$(cat "$MINIO_ACCESS_KEY_FILE")"
  secret="$(cat "$MINIO_SECRET_KEY_FILE")"
  mc alias set restore "$MINIO_ENDPOINT" "$access" "$secret" >/dev/null
  while IFS= read -r bucket; do
    [ -n "$bucket" ] || continue
    mc mb --ignore-existing "restore/$bucket" >/dev/null
    mc mirror --overwrite --remove "/backup/objects/$bucket" "restore/$bucket"
  done < /backup/buckets.txt
'

pige_info "restaurando o volume persistente de arquivos locais dos tenants"
pige_compose run --rm --no-deps --no-build --user 0:0 -v "$archive:/backup:ro" \
  --entrypoint python pige360-app-init -c '
from pathlib import Path, PurePosixPath
import shutil
import tarfile

target = Path("/var/lib/pige360/tenants")
target.mkdir(parents=True, exist_ok=True)
with tarfile.open("/backup/tenant-storage.tar.gz", "r:gz") as archive:
    for member in archive.getmembers():
        path = PurePosixPath(member.name)
        if not member.name or path.is_absolute() or ".." in path.parts or member.issym() or member.islnk() or member.isdev():
            raise SystemExit(f"entrada insegura no tenant storage: {member.name!r}")
    for item in target.iterdir():
        if item.is_dir() and not item.is_symlink():
            shutil.rmtree(item)
        else:
            item.unlink()
    archive.extractall(target, filter="data")
'

pige_info "aplicando migrations idempotentes após a importação"
pige_compose run --rm --no-deps --no-build pige360-app-init
pige_compose up -d --no-build --remove-orphans
sh "$PIGE360_ROOT/deploy/self-hosted/healthcheck.sh"

restore_failed=false
pige_info "restauração concluída e validada por readiness"
pige_info "o snapshot MinIO contém objetos atuais; histórico de versões não integra este formato v1"
