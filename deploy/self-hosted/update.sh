#!/bin/sh
set -eu

script_root="$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)"
package="${1:-}"
[ -n "$package" ] || { printf '%s\n' "Uso: $0 DIRETORIO_DA_NOVA_VERSAO" >&2; exit 2; }
case "$package" in
  /*) ;;
  *) package="$(pwd -P)/$package" ;;
esac
package="$(CDPATH= cd -- "$package" && pwd)"
current="${PIGE360_CURRENT_ROOT:-$script_root}"
current="$(CDPATH= cd -- "$current" && pwd)"
[ "$package" != "$current" ] || { printf '%s\n' 'A versão candidata deve estar em outro diretório.' >&2; exit 2; }
for required in \
  VERSION compose.yaml compose.production.yaml \
  deploy/self-hosted/install.sh deploy/self-hosted/lib.sh deploy/self-hosted/build-images.sh \
  deploy/self-hosted/healthcheck.sh deploy/self-hosted/backup.sh deploy/self-hosted/restore.sh \
  deploy/self-hosted/rollback.sh scripts/local/init-secrets.sh scripts/backup/backup_manifest.py \
  infra/docker/Dockerfile.api infra/docker/Dockerfile.migrations infra/docker/Dockerfile.worker \
  infra/docker/Dockerfile.web backend/app/shared/database/migrate_tenants.py; do
  [ -f "$package/$required" ] || {
    printf '%s\n' "Pacote candidato inválido; arquivo ausente: $required" >&2
    exit 2
  }
done
command -v python3 >/dev/null 2>&1 || { printf '%s\n' 'python3 é obrigatório.' >&2; exit 3; }

PIGE360_ENV_FILE="${PIGE360_ENV_FILE:-$current/.env}"
PIGE360_SECRETS_DIR="${PIGE360_SECRETS_DIR:-$current/runtime-secrets}"
PIGE360_DEPLOY_TARGET="${PIGE360_DEPLOY_TARGET:-base}"
PIGE360_IMAGE_MODE="${PIGE360_IMAGE_MODE:-source}"
state_dir="${PIGE360_STATE_DIR:-$(dirname -- "$current")/.pige360-deploy}"
PIGE360_STATE_DIR="$state_dir"
current_link="${PIGE360_CURRENT_LINK:-$state_dir/current}"
[ ! -e "$current_link" ] || [ -L "$current_link" ] || {
  printf '%s\n' "Ponteiro current deve ser ausente ou link simbólico: $current_link" >&2
  exit 2
}
timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
backup_dir="$state_dir/backups/pre-update-$timestamp"
history_dir="$state_dir/history"
pending="$state_dir/pending-$timestamp.json"
record="$history_dir/update-$timestamp.json"
mkdir -p "$history_dir" "$state_dir/backups" "$(dirname -- "$current_link")"

previous_version="$(tr -d '[:space:]' < "$current/VERSION")"
candidate_version="$(tr -d '[:space:]' < "$package/VERSION")"
python3 - "$previous_version" "$candidate_version" "${PIGE360_ALLOW_DOWNGRADE:-false}" <<'PY'
import re
import sys

pattern = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")
previous, candidate, allow_downgrade = sys.argv[1:]
if not pattern.fullmatch(previous) or not pattern.fullmatch(candidate):
    raise SystemExit("VERSION anterior/candidata não segue SemVer")
if previous == candidate:
    raise SystemExit("A versão candidata é igual à versão instalada")
prev_core = tuple(map(int, previous.split(".")))
candidate_core = tuple(map(int, candidate.split(".")))
if candidate_core < prev_core and allow_downgrade != "true":
    raise SystemExit("Downgrade recusado; use rollback ou PIGE360_ALLOW_DOWNGRADE=true")
PY
PIGE360_IMAGE_TAG="$previous_version"
APP_VERSION="$previous_version"
export PIGE360_ENV_FILE PIGE360_SECRETS_DIR PIGE360_DEPLOY_TARGET PIGE360_IMAGE_MODE
export PIGE360_STATE_DIR PIGE360_IMAGE_TAG APP_VERSION

. "$current/deploy/self-hosted/lib.sh"
PIGE360_ROOT="$current"
export PIGE360_ROOT
pige_prepare_context
pige_acquire_operation_lock
trap pige_release_operation_lock EXIT

PIGE360_ROOT="$current" sh "$current/deploy/self-hosted/backup.sh" "$backup_dir"
python3 - "$pending" "$current" "$package" "$backup_dir" "$PIGE360_ENV_FILE" "$PIGE360_SECRETS_DIR" \
  "$PIGE360_DEPLOY_TARGET" "$PIGE360_IMAGE_MODE" "$previous_version" "$candidate_version" "$state_dir" "$current_link" <<'PY'
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

keys = (
    "previous_root", "candidate_root", "backup", "env_file", "secrets_dir",
    "deployment_target", "image_mode", "previous_version", "candidate_version",
    "state_dir", "current_link",
)
record = dict(zip(keys, sys.argv[2:], strict=True))
record.update({"schema_version": 1, "status": "pending", "created_at": datetime.now(timezone.utc).isoformat()})
Path(sys.argv[1]).write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
PY

printf '%s\n' "PIGE360: atualizando $previous_version -> $candidate_version"
if ! PIGE360_ROOT="$package" PIGE360_IMAGE_TAG="$candidate_version" APP_VERSION="$candidate_version" \
  sh "$package/deploy/self-hosted/install.sh" \
  --mode "$PIGE360_IMAGE_MODE" --target "$PIGE360_DEPLOY_TARGET"; then
  printf '%s\n' "ERRO: atualização falhou; backup preservado em $backup_dir" >&2
  printf '%s\n' "Use rollback.sh $pending --with-data --confirm RESTORE-PIGE360 após diagnosticar a falha." >&2
  exit 1
fi

current_link_tmp="${current_link}.tmp.$$"
[ ! -e "$current_link_tmp" ] || { printf '%s\n' "Link temporário já existe: $current_link_tmp" >&2; exit 2; }
ln -s "$package" "$current_link_tmp"
python3 -c 'import os,sys; os.replace(sys.argv[1], sys.argv[2])' "$current_link_tmp" "$current_link"

python3 - "$pending" <<'PY'
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

path = Path(sys.argv[1])
record = json.loads(path.read_text(encoding="utf-8"))
record["status"] = "completed"
record["completed_at"] = datetime.now(timezone.utc).isoformat()
path.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
PY
mv "$pending" "$record"
printf '%s\n' "PIGE360: atualização concluída; estado registrado em $record"
