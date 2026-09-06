#!/bin/sh
set -eu

root="$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)"
email="${1:-}"
password_file=""

usage() {
  printf '%s\n' "Uso: $0 EMAIL [--password-file ARQUIVO|-]"
}

case "$email" in
  -h|--help) usage; exit 0 ;;
esac
[ -n "$email" ] || { usage >&2; exit 2; }
shift
while [ "$#" -gt 0 ]; do
  case "$1" in
    --password-file) [ "$#" -ge 2 ] || { usage >&2; exit 2; }; password_file="$2"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) usage >&2; exit 2 ;;
  esac
done

PIGE360_ROOT="${PIGE360_ROOT:-$root}"
export PIGE360_ROOT
. "$root/deploy/self-hosted/lib.sh"
pige_prepare_context
command -v python3 >/dev/null 2>&1 || pige_die "python3 é obrigatório para o bootstrap administrativo."

if [ -n "$password_file" ]; then
  if [ "$password_file" = - ]; then
    IFS= read -r password
  else
    [ -f "$password_file" ] || pige_die "arquivo de senha ausente: $password_file"
    IFS= read -r password < "$password_file"
  fi
else
  [ -t 0 ] || pige_die "stdin não interativo; use --password-file ARQUIVO ou --password-file -"
  printf '%s' 'Senha inicial do administrador (mínimo 10 caracteres): ' >&2
  trap 'stty echo 2>/dev/null || true; printf "\n" >&2' EXIT HUP INT TERM
  stty -echo
  IFS= read -r password
  stty echo
  printf '\n' >&2
  trap - EXIT HUP INT TERM
fi

[ "${#password}" -ge 10 ] || pige_die "a senha inicial deve ter ao menos 10 caracteres."
api_port="$(pige_resolve_nonempty API_PUBLISHED_PORT 58000)"
platform_host="$(pige_resolve_nonempty PLATFORM_CONSOLE_HOST console.pige360.com.br)"
bootstrap_token_file="$PIGE360_SECRETS_DIR/bootstrap_token.txt"
[ -s "$bootstrap_token_file" ] || pige_die "token de bootstrap ausente: $bootstrap_token_file"
password_tmp="$(mktemp "${TMPDIR:-/tmp}/pige360-bootstrap-password.XXXXXX")"
chmod 600 "$password_tmp"
trap 'rm -f "$password_tmp"' EXIT HUP INT TERM
printf '%s' "$password" > "$password_tmp"
password=''

python3 - "$email" "$platform_host" "$api_port" "$bootstrap_token_file" "$password_tmp" <<'PY'
from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

email, host, port, token_path, password_path = sys.argv[1:]
password = Path(password_path).read_text(encoding="utf-8")
token = Path(token_path).read_text(encoding="utf-8").strip()
payload = json.dumps({"email": email, "password": password}).encode("utf-8")
request = urllib.request.Request(
    f"http://127.0.0.1:{port}/api/v1/platform/bootstrap",
    data=payload,
    method="POST",
    headers={
        "Content-Type": "application/json",
        "Host": host,
        "X-Bootstrap-Token": token,
    },
)
try:
    with urllib.request.urlopen(request, timeout=20) as response:
        body = json.load(response)
except urllib.error.HTTPError as exc:
    detail = exc.read().decode("utf-8", errors="replace")
    raise SystemExit(f"bootstrap recusado (HTTP {exc.code}): {detail}") from exc
status = body.get("status")
if status not in {"bootstrapped", "already_bootstrapped"}:
    raise SystemExit(f"resposta inesperada do bootstrap: {body}")
print(json.dumps({"status": status, "admin": body.get("admin")}, ensure_ascii=False))
PY
rm -f "$password_tmp"
trap - EXIT HUP INT TERM

pige_info "bootstrap administrativo concluído de forma idempotente para $email"
