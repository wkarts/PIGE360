#!/bin/sh
set -eu
if [ "$#" -eq 0 ]; then
  set -- --output-dir release/output
fi
exec python3 scripts/release/package_local.py "$@"
