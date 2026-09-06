#!/usr/bin/env bash
set -euo pipefail
APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
"$APP_DIR/stop.sh" || true
"$APP_DIR/start.sh"
