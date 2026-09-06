#!/usr/bin/env bash
set -euo pipefail
APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_DIR="$APP_DIR/logs"
mkdir -p "$LOG_DIR"

if ! "$APP_DIR/status.sh" >/dev/null 2>&1; then
  echo "[$(date -Is)] offline; reiniciando" >> "$LOG_DIR/check.log"
  "$APP_DIR/start.sh" >> "$LOG_DIR/check.log" 2>&1
  exit 0
fi

# Health-check da API interna. Se falhar, reinicia.
set -a
[[ -f "$APP_DIR/.env" ]] && source "$APP_DIR/.env"
set +a
API_HOST="${PIGE360_DEPLOYER_API_HOST:-127.0.0.1}"
API_PORT="${PIGE360_DEPLOYER_API_PORT:-61001}"

if command -v curl >/dev/null 2>&1; then
  if ! curl -fsS --max-time 5 "http://$API_HOST:$API_PORT/health" >/dev/null; then
    echo "[$(date -Is)] health falhou; reiniciando" >> "$LOG_DIR/check.log"
    "$APP_DIR/restart.sh" >> "$LOG_DIR/check.log" 2>&1
  fi
fi
