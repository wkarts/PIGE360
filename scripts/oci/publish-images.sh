#!/usr/bin/env bash
set -euo pipefail

root_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$root_dir"
. "$root_dir/scripts/oci/image-catalog.sh"

mode="${1:-}"
manifest_dir="${2:-release/artifacts/docker/runtime}"
source_tag="${PIGE360_IMAGE_TAG:-$(tr -d '[:space:]' < VERSION)}"
owner="${GITHUB_REPOSITORY_OWNER:-wkarts}"
registry="${PIGE360_GHCR_NAMESPACE:-ghcr.io/${owner}}"
registry="$(printf '%s' "$registry" | tr '[:upper:]' '[:lower:]')"
commit_sha="${PIGE360_PUBLISH_SHA:-${GITHUB_SHA:-$(git rev-parse HEAD)}}"

[[ "$commit_sha" =~ ^[0-9a-fA-F]{12,64}$ ]] || {
  echo "SHA inválido para publicação OCI: ${commit_sha}" >&2
  exit 2
}
short_sha="${commit_sha:0:12}"

case "$mode" in
  develop)
    channel="develop"
    immutable_tag="develop-${short_sha}"
    channel_tags=(develop)
    manifest_path="${manifest_dir}/ghcr-develop-manifest.json"
    release_version=""
    ;;
  release)
    channel="release"
    release_version="${PIGE360_RELEASE_VERSION:-$(tr -d '[:space:]' < VERSION)}"
    semver_re='^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)(-[0-9A-Za-z-]+(\.[0-9A-Za-z-]+)*)?$'
    [[ "$release_version" =~ $semver_re ]] || {
      echo "Versão OCI inválida; use SemVer sem build metadata (+): ${release_version}" >&2
      exit 2
    }
    [[ "$source_tag" == "$release_version" ]] || {
      echo "A tag local (${source_tag}) diverge da release (${release_version})." >&2
      exit 2
    }
    immutable_tag="release-${short_sha}"
    channel_tags=("${release_version}" "v${release_version}")
    manifest_path="${manifest_dir}/ghcr-release-manifest.json"
    ;;
  *)
    echo "Uso: $0 develop|release [diretório-do-manifesto]" >&2
    exit 2
    ;;
esac

mkdir -p "$manifest_dir"
records_file="$(mktemp)"
trap 'rm -f "$records_file"' EXIT
: > "$records_file"

registry_digest() {
  local ref="$1"
  local raw_file digest
  raw_file="$(mktemp)"
  if ! docker buildx imagetools inspect "$ref" --raw > "$raw_file" 2>/dev/null; then
    rm -f "$raw_file"
    return 1
  fi
  digest="$(sha256sum "$raw_file" | awk '{print $1}')"
  rm -f "$raw_file"
  printf 'sha256:%s\n' "$digest"
}

registry_config_digest() {
  local ref="$1"
  local raw_file
  raw_file="$(mktemp)"
  if ! docker buildx imagetools inspect "$ref" --raw > "$raw_file" 2>/dev/null; then
    rm -f "$raw_file"
    return 1
  fi
  python3 - "$raw_file" <<'PY'
import json
import sys
from pathlib import Path

payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
digest = payload.get("config", {}).get("digest")
if not isinstance(digest, str) or not digest.startswith("sha256:"):
    raise SystemExit(1)
print(digest)
PY
  status=$?
  rm -f "$raw_file"
  return "$status"
}

echo "Publicando imagens OCI do PIGE360"
echo "  modo       : ${mode}"
echo "  namespace  : ${registry}"
echo "  commit     : ${commit_sha}"
echo "  tag local  : ${source_tag}"
echo "  tag imutável: ${immutable_tag}"

# Pré-flight completo: nenhuma publicação começa se uma imagem local estiver
# ausente. Isso evita alterar apenas parte do conjunto por erro de build.
for image in "${PIGE360_ALL_IMAGE_NAMES[@]}"; do
  docker image inspect "${image}:${source_tag}" >/dev/null 2>&1 || {
    echo "Imagem local obrigatória ausente: ${image}:${source_tag}" >&2
    exit 10
  }
done

declare -A immutable_digests=()

# Fase 1: publica e confirma todas as referências rastreáveis. O canal móvel
# develop e as tags SemVer só são tocados depois que o conjunto inteiro existe.
for image in "${PIGE360_ALL_IMAGE_NAMES[@]}"; do
  local_ref="${image}:${source_tag}"
  immutable_ref="${registry}/${image}:${immutable_tag}"
  local_config_digest="$(docker image inspect --format '{{.Id}}' "$local_ref")"
  echo "::group::${image} — referência imutável"
  if digest="$(registry_digest "$immutable_ref")"; then
    remote_config_digest="$(registry_config_digest "$immutable_ref")" || {
      echo "Referência imutável remota não é uma imagem OCI simples verificável: ${immutable_ref}" >&2
      exit 14
    }
    [[ "$remote_config_digest" == "$local_config_digest" ]] || {
      echo "Referência imutável remota diverge da imagem local e não será sobrescrita: ${immutable_ref}" >&2
      exit 14
    }
    echo "Referência imutável existente preservada: ${immutable_ref}"
  else
    docker tag "$local_ref" "$immutable_ref"
    docker push "$immutable_ref"
    digest="$(registry_digest "$immutable_ref")" || {
      echo "Não foi possível confirmar a referência publicada: ${immutable_ref}" >&2
      exit 11
    }
    remote_config_digest="$(registry_config_digest "$immutable_ref")" || {
      echo "Não foi possível confirmar o config digest publicado: ${immutable_ref}" >&2
      exit 11
    }
    [[ "$remote_config_digest" == "$local_config_digest" ]] || {
      echo "Config digest divergente após publicação: ${immutable_ref}" >&2
      exit 11
    }
  fi
  immutable_digests["$image"]="$digest"
  printf '%s\t%s\t%s\n' "$image" "$immutable_ref" "$digest" >> "$records_file"
  echo "Digest: ${digest}"
  echo "::endgroup::"
done

# Tags de release são imutáveis. A verificação global ocorre antes da fase 2,
# evitando sobrescrever uma versão já existente com conteúdo divergente.
if [[ "$mode" == release ]]; then
  for image in "${PIGE360_ALL_IMAGE_NAMES[@]}"; do
    for tag in "${channel_tags[@]}"; do
      channel_ref="${registry}/${image}:${tag}"
      if existing_digest="$(registry_digest "$channel_ref")"; then
        [[ "$existing_digest" == "${immutable_digests[$image]}" ]] || {
          echo "Tag SemVer remota divergente recusada: ${channel_ref}" >&2
          exit 12
        }
      fi
    done
  done
fi

# Fase 2: somente após todas as imagens imutáveis estarem disponíveis, avança
# o canal develop ou materializa as duas grafias SemVer da release.
for image in "${PIGE360_ALL_IMAGE_NAMES[@]}"; do
  immutable_ref="${registry}/${image}:${immutable_tag}"
  for tag in "${channel_tags[@]}"; do
    channel_ref="${registry}/${image}:${tag}"
    echo "::group::${image} — ${channel_ref}"
    if existing_digest="$(registry_digest "$channel_ref")" && \
       [[ "$existing_digest" == "${immutable_digests[$image]}" ]]; then
      echo "Canal já aponta para o digest esperado: ${channel_ref}"
    else
      # Promove no próprio registry a referência já validada. `prefer-index`
      # desabilitado preserva o manifesto original em vez de envolvê-lo em um
      # novo índice com digest diferente.
      docker buildx imagetools create --prefer-index=false \
        --tag "$channel_ref" "$immutable_ref"
    fi
    channel_digest="$(registry_digest "$channel_ref")" || {
      echo "Não foi possível confirmar o canal publicado: ${channel_ref}" >&2
      exit 13
    }
    [[ "$channel_digest" == "${immutable_digests[$image]}" ]] || {
      echo "Digest divergente após publicação: ${channel_ref}" >&2
      exit 13
    }
    echo "Digest confirmado: ${channel_digest}"
    echo "::endgroup::"
  done
done

channel_tags_csv="$(IFS=,; printf '%s' "${channel_tags[*]}")"
python3 - "$manifest_path" "$mode" "$channel" "$registry" "$commit_sha" \
  "$source_tag" "$immutable_tag" "$channel_tags_csv" "$release_version" "$records_file" <<'PY'
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

(
    manifest_path,
    mode,
    channel,
    registry,
    commit_sha,
    source_tag,
    immutable_tag,
    channel_tags_csv,
    release_version,
    records_path,
) = sys.argv[1:]

channel_tags = channel_tags_csv.split(",")
images = []
for line in Path(records_path).read_text(encoding="utf-8").splitlines():
    if not line.strip():
        continue
    name, immutable_ref, digest = line.split("\t")
    channel_refs = [f"{registry}/{name}:{tag}" for tag in channel_tags]
    images.append(
        {
            "name": name,
            "moving_ref": channel_refs[0],
            "channel_refs": channel_refs,
            "immutable_ref": immutable_ref,
            "digest": digest,
            "digest_ref": f"{registry}/{name}@{digest}",
        }
    )

payload = {
    "schema_version": 2,
    "mode": mode,
    "channel": channel,
    # GHCR does not offer one atomic transaction spanning multiple packages.
    # The publisher therefore uses an explicit two-phase strategy: every
    # immutable SHA reference is confirmed before any channel tag is promoted.
    "publication_strategy": "two-phase-immutable-first",
    "cross_image_atomicity": False,
    "registry": registry,
    "source_image_tag": source_tag,
    "immutable_tag": immutable_tag,
    "channel_tags": channel_tags,
    "commit_sha": commit_sha,
    "generated_at": datetime.now(timezone.utc).isoformat(),
    "images": images,
}
if release_version:
    payload["release_version"] = release_version

Path(manifest_path).write_text(
    json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
)
PY

echo "Publicação concluída: ${#PIGE360_ALL_IMAGE_NAMES[@]} imagens."
echo "Manifesto com digests: ${manifest_path}"
