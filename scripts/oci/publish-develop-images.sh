#!/usr/bin/env bash
set -euo pipefail

root_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$root_dir"

source_tag="${PIGE360_IMAGE_TAG:-$(tr -d '[:space:]' < VERSION)}"
owner="${GITHUB_REPOSITORY_OWNER:-wkarts}"
owner="$(printf '%s' "$owner" | tr '[:upper:]' '[:lower:]')"
registry="${PIGE360_GHCR_NAMESPACE:-ghcr.io/${owner}}"
commit_sha="${GITHUB_SHA:-$(git rev-parse HEAD)}"
short_sha="${commit_sha:0:12}"
channel="develop"

images=(
  pige360-base-python
  pige360-base-node
  pige360-base-runtime
  pige360-base-rust-tauri
  pige360-api
  pige360-web
  pige360-platform-console
  pige360-branding-studio
  pige360-tenant-download-center
  pige360-worker
  pige360-migrations
  pige360-reporting
)

manifest_dir="${1:-release/artifacts/docker/runtime}"
manifest_path="${manifest_dir}/ghcr-develop-manifest.json"
mkdir -p "$manifest_dir"

echo "Publicando imagens de develop/homologação do PIGE360 no GHCR"
echo "  namespace : ${registry}"
echo "  canal     : ${channel}"
echo "  commit    : ${commit_sha}"
echo "  source tag: ${source_tag}"

records_file="$(mktemp)"
trap 'rm -f "$records_file"' EXIT
: > "$records_file"

for image in "${images[@]}"; do
  local_ref="${image}:${source_tag}"
  moving_ref="${registry}/${image}:${channel}"
  immutable_ref="${registry}/${image}:${channel}-${short_sha}"

  docker image inspect "$local_ref" >/dev/null 2>&1 || {
    echo "Imagem local obrigatória ausente: ${local_ref}" >&2
    exit 10
  }

  echo "::group::${image}"
  echo "Tag móvel     : ${moving_ref}"
  echo "Tag rastreável: ${immutable_ref}"
  docker tag "$local_ref" "$moving_ref"
  docker tag "$local_ref" "$immutable_ref"
  docker push "$immutable_ref"
  docker push "$moving_ref"
  docker buildx imagetools inspect "$immutable_ref" >/dev/null
  printf '%s\t%s\t%s\n' "$image" "$moving_ref" "$immutable_ref" >> "$records_file"
  echo "::endgroup::"
done

python3 - "$manifest_path" "$registry" "$commit_sha" "$source_tag" "$records_file" <<'PY'
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

manifest_path = Path(sys.argv[1])
registry = sys.argv[2]
commit_sha = sys.argv[3]
source_tag = sys.argv[4]
records_path = Path(sys.argv[5])

images = []
for line in records_path.read_text(encoding="utf-8").splitlines():
    if not line.strip():
        continue
    name, moving_ref, immutable_ref = line.split("\t")
    images.append({
        "name": name,
        "moving_ref": moving_ref,
        "immutable_ref": immutable_ref,
    })

manifest_path.write_text(json.dumps({
    "schema_version": 1,
    "channel": "develop",
    "registry": registry,
    "source_image_tag": source_tag,
    "commit_sha": commit_sha,
    "generated_at": datetime.now(timezone.utc).isoformat(),
    "images": images,
}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
PY

echo "Publicação concluída: ${#images[@]} imagens."
echo "Manifesto: ${manifest_path}"
