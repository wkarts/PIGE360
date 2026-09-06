#!/bin/sh
set -eu

root="$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)"
PIGE360_ROOT="${PIGE360_ROOT:-$root}"
. "$root/deploy/self-hosted/lib.sh"
pige_prepare_context
pige_require_docker

attempts="${PIGE360_READINESS_ATTEMPTS:-30}"
delay="${PIGE360_READINESS_DELAY_SECONDS:-5}"

pige_runtime_ready() {
  pige_compose exec -T pige360-api python -c \
    "import urllib.request; r=urllib.request.Request('http://127.0.0.1:8000/api/v1/health/ready', headers={'Host':'console.platform.local'}); urllib.request.urlopen(r, timeout=5)" \
    >/dev/null 2>&1 || return 1

  for pige_ui_service in \
    pige360-web pige360-platform-console pige360-branding-studio pige360-tenant-download-center; do
    pige_compose exec -T "$pige_ui_service" /bin/sh -ec \
      "wget -q -O- http://127.0.0.1:8080/healthz | grep -qx ok" \
      >/dev/null 2>&1 || return 1
  done

  pige_compose exec -T pige360-worker-default python -c \
    "from pathlib import Path; c=Path('/proc/1/cmdline').read_bytes().replace(b'\\0', b' '); assert b'celery' in c and b'worker' in c" \
    >/dev/null 2>&1 || return 1
  pige_compose exec -T pige360-beat python -c \
    "from pathlib import Path; c=Path('/proc/1/cmdline').read_bytes().replace(b'\\0', b' '); assert b'celery' in c and b'beat' in c" \
    >/dev/null 2>&1 || return 1
}

current=1
while [ "$current" -le "$attempts" ]; do
  if pige_runtime_ready; then
    pige_info "readiness aprovado: API, quatro UIs, worker consolidado e beat"
    exit 0
  fi
  [ "$current" -eq "$attempts" ] || sleep "$delay"
  current=$((current + 1))
done

pige_compose ps >&2 || true
pige_compose logs --no-color --tail=120 \
  pige360-app-init pige360-api pige360-web pige360-platform-console \
  pige360-branding-studio pige360-tenant-download-center \
  pige360-worker-default pige360-beat >&2 || true
pige_die "stack não atingiu readiness completo após $attempts tentativas."
