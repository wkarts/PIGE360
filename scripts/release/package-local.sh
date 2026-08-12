#!/bin/sh
set -eu
exec python3 scripts/release/package_local.py "$@"
