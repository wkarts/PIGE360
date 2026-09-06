#!/usr/bin/env bash
set -euo pipefail

root_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
exec bash "$root_dir/scripts/oci/publish-images.sh" release \
  "${1:-release/artifacts/docker/release}"
