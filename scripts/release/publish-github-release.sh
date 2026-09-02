#!/usr/bin/env bash
set -euo pipefail

if [[ "${REMOTE_RELEASE_ENABLED:-false}" != "true" ]]; then
  echo "REMOTE_RELEASE_ENABLED não está habilitado; publicação recusada." >&2
  exit 78
fi
command -v gh >/dev/null 2>&1 || { echo "GitHub CLI (gh) é obrigatório." >&2; exit 3; }
: "${GITHUB_TOKEN:?GITHUB_TOKEN ausente}"

version="$(tr -d '[:space:]' < VERSION)"
tag="${RELEASE_TAG:-v${version}}"
assets_dir="${1:-release/output}"
[[ "$version" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] || { echo "VERSION inválida: $version. Use somente SemVer estável X.Y.Z." >&2; exit 2; }
[[ "$tag" == "v$version" ]] || { echo "Tag inválida para a versão canônica: $tag" >&2; exit 2; }

stage="$assets_dir/.github-release-assets"
rm -rf "$stage"
mkdir -p "$stage"

asset_source_id() {
  local asset="$1"
  local relative source_dir source_id
  relative="${asset#"$assets_dir"/}"
  source_dir="$(dirname "$relative")"
  source_id="$(printf '%s' "$source_dir" | sed -E 's/[^A-Za-z0-9._-]+/-/g; s/^-+//; s/-+$//')"
  [[ -n "$source_id" && "$source_id" != "." ]] || source_id="asset"
  printf '%s' "$source_id"
}

asset_with_digest_suffix() {
  local filename="$1"
  local digest="$2"
  local stem extension
  if [[ "$filename" == *.* ]]; then
    stem="${filename%.*}"
    extension=".${filename##*.}"
  else
    stem="$filename"
    extension=""
  fi
  printf '%s-%s%s' "$stem" "${digest:0:12}" "$extension"
}

while IFS= read -r -d '' asset; do
  filename="$(basename "$asset")"
  if [[ "$filename" == "SHA256SUMS" ]]; then
    filename="$(basename "$(dirname "$asset")")-SHA256SUMS"
  fi
  destination="$stage/$filename"
  if [[ -e "$destination" ]]; then
    if cmp -s "$asset" "$destination"; then
      echo "Artefato idêntico deduplicado: $filename"
      continue
    fi
    source_id="$(asset_source_id "$asset")"
    filename="$source_id--$filename"
    destination="$stage/$filename"
    if [[ -e "$destination" ]]; then
      if cmp -s "$asset" "$destination"; then
        echo "Artefato idêntico deduplicado: $filename"
        continue
      fi
      filename="$(asset_with_digest_suffix "$filename" "$(sha256sum "$asset" | awk '{print $1}')")"
      destination="$stage/$filename"
      [[ ! -e "$destination" ]] || {
        echo "Colisão irrecuperável de nome de artefato: $filename" >&2
        exit 4
      }
    fi
    echo "Artefato com nome repetido preservado como: $filename"
  fi
  cp "$asset" "$destination"
done < <(find "$assets_dir" -type f \( -name '*.zip' -o -name '*.tar' -o -name '*.json' -o -name '*.pdf' -o -name '*SHA256SUMS' \) -not -path "$stage/*" -print0 | sort -z)

mapfile -t assets < <(find "$stage" -maxdepth 1 -type f -print | sort)
((${#assets[@]} > 0)) || { echo "Nenhum artefato publicável encontrado em $assets_dir" >&2; exit 4; }

notes="${RELEASE_NOTES_FILE:-release/RELEASE_NOTES.md}"
if gh release view "$tag" >/dev/null 2>&1; then
  remote_assets="$(gh release view "$tag" --json assets --jq '.assets[].name')"
  missing=0
  for asset in "${assets[@]}"; do
    if ! grep -Fqx -- "$(basename "$asset")" <<<"$remote_assets"; then
      echo "A release $tag existe, mas não contém o asset esperado: $(basename "$asset")" >&2
      missing=1
    fi
  done
  if ((missing == 0)); then
    echo "A release $tag já contém todos os assets esperados; versões publicadas são imutáveis."
    exit 0
  fi
  echo "A release $tag é incompleta; versões publicadas são imutáveis e exigem intervenção explícita." >&2
  exit 5
fi

target="${RELEASE_TARGET_SHA:-${GITHUB_SHA:?GITHUB_SHA ausente}}"
args=(release create "$tag" "${assets[@]}" --title "PIGE360 $version" --target "$target")
[[ -f "$notes" ]] && args+=(--notes-file "$notes") || args+=(--generate-notes)
gh "${args[@]}"
