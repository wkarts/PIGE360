#!/bin/sh
set -eu

root="$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)"
state=""
mode=""
confirmation=""

usage() {
  printf '%s\n' "Uso: $0 [ARQUIVO_DE_ESTADO] (--application-only --confirm APP-ONLY-COMPATIBLE | --with-data --confirm RESTORE-PIGE360)"
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --application-only) mode=application; shift ;;
    --with-data) mode=data; shift ;;
    --confirm) [ "$#" -ge 2 ] || { usage >&2; exit 2; }; confirmation="$2"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    -*) usage >&2; exit 2 ;;
    *) [ -z "$state" ] || { usage >&2; exit 2; }; state="$1"; shift ;;
  esac
done
[ -n "$mode" ] || { usage >&2; exit 2; }
command -v python3 >/dev/null 2>&1 || { printf '%s\n' 'python3 é obrigatório.' >&2; exit 3; }

if [ -z "$state" ]; then
  state_dir="${PIGE360_STATE_DIR:-$(dirname -- "$root")/.pige360-deploy}"
  state="$(find "$state_dir/history" -maxdepth 1 -type f -name 'update-*.json' -print 2>/dev/null | LC_ALL=C sort | tail -1)"
fi
[ -n "$state" ] && [ -f "$state" ] || { printf '%s\n' 'Estado de atualização não encontrado.' >&2; exit 2; }

state_value() {
  python3 -c 'import json,sys; value=json.load(open(sys.argv[1], encoding="utf-8"))[sys.argv[2]]; print(value)' "$state" "$1"
}
previous_root="$(state_value previous_root)"
previous_version="$(state_value previous_version)"
backup="$(state_value backup)"
PIGE360_ENV_FILE="$(state_value env_file)"
PIGE360_SECRETS_DIR="$(state_value secrets_dir)"
PIGE360_DEPLOY_TARGET="$(state_value deployment_target)"
PIGE360_IMAGE_MODE="$(state_value image_mode)"
PIGE360_STATE_DIR="$(state_value state_dir)"
recorded_current_link="$(state_value current_link)"
export PIGE360_ENV_FILE PIGE360_SECRETS_DIR PIGE360_DEPLOY_TARGET PIGE360_IMAGE_MODE PIGE360_STATE_DIR
[ -f "$previous_root/deploy/self-hosted/install.sh" ] || { printf '%s\n' 'Versão anterior indisponível.' >&2; exit 2; }
current_link="${PIGE360_CURRENT_LINK:-$recorded_current_link}"
[ ! -e "$current_link" ] || [ -L "$current_link" ] || {
  printf '%s\n' "Ponteiro current deve ser ausente ou link simbólico: $current_link" >&2
  exit 2
}

case "$mode" in
  application)
    [ "$confirmation" = APP-ONLY-COMPATIBLE ] || {
      printf '%s\n' 'Rollback de aplicação exige --confirm APP-ONLY-COMPATIBLE.' >&2
      exit 78
    }
    printf '%s\n' 'PIGE360: rollback somente da aplicação; nenhum downgrade de schema será executado.'
    PIGE360_ROOT="$previous_root" PIGE360_IMAGE_TAG="$previous_version" APP_VERSION="$previous_version" \
      sh "$previous_root/deploy/self-hosted/install.sh" \
      --mode "$PIGE360_IMAGE_MODE" --target "$PIGE360_DEPLOY_TARGET" --skip-migrations
    ;;
  data)
    [ "$confirmation" = RESTORE-PIGE360 ] || {
      printf '%s\n' 'Rollback com dados exige --confirm RESTORE-PIGE360.' >&2
      exit 78
    }
    [ -d "$backup" ] || { printf '%s\n' 'Backup pré-update indisponível.' >&2; exit 2; }
    PIGE360_ROOT="$previous_root" PIGE360_IMAGE_TAG="$previous_version" APP_VERSION="$previous_version" \
      sh "$root/deploy/self-hosted/restore.sh" \
      "$backup" --confirm RESTORE-PIGE360
    ;;
esac

mkdir -p "$(dirname -- "$current_link")"
current_link_tmp="${current_link}.tmp.$$"
[ ! -e "$current_link_tmp" ] || { printf '%s\n' "Link temporário já existe: $current_link_tmp" >&2; exit 2; }
ln -s "$previous_root" "$current_link_tmp"
python3 -c 'import os,sys; os.replace(sys.argv[1], sys.argv[2])' "$current_link_tmp" "$current_link"
printf '%s\n' "PIGE360: rollback concluído para $(tr -d '[:space:]' < "$previous_root/VERSION")"
