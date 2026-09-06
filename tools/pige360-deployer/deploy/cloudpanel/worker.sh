#!/usr/bin/env bash
set -euo pipefail
APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
set -a
[[ -f "$APP_DIR/.env" ]] && source "$APP_DIR/.env"
set +a
BIN_PATH="${PIGE360_DEPLOYER_BINARY:-$APP_DIR/bin/pige360_deployer}"
if [[ "$BIN_PATH" != /* ]]; then
  BIN_PATH="$APP_DIR/${BIN_PATH#./}"
fi
export PIGE360_DEPLOYER_ENV_FILE="${PIGE360_DEPLOYER_ENV_FILE:-$APP_DIR/.env}"
export PIGE360_DEPLOYER_DATA_DIR="${PIGE360_DEPLOYER_DATA_DIR:-$APP_DIR/data}"
"$BIN_PATH" --mode=worker --data-dir "$PIGE360_DEPLOYER_DATA_DIR" "$@"
