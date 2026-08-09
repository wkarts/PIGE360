#!/bin/sh
set -eu
exec python3 scripts/oci/build_structural_oci.py "$@"
