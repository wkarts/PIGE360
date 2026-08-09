#!/bin/sh
set -eu
dir="${1:-/mnt/data/PIGE360_V8_LOCAL_DELIVERY}"
find "$dir" -maxdepth 1 -type f ! -name SHA256SUMS -printf '%f\n' | sort | while read -r file; do sha256sum "$dir/$file"; done | sed "s#  $dir/#  #" > "$dir/SHA256SUMS"
