#!/bin/sh
set -eu
exec python3 scripts/ci/run_all.py "$@"
