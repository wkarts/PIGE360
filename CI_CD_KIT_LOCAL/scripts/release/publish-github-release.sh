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
[[ "$version" =~ ^[0-9]+\.[0-9]+\.[0-9]+-alpha\.[0-9]+$ ]] || { echo "VERSION inválida: $version" >&2; exit 2; }

stage="$assets_dir/.github-release-assets"
rm -rf "$stage"
mkdir -p "$stage"
while IFS= read -r -d '' asset; do
  filename="$(basename "$asset")"
  if [[ "$filename" == "SHA256SUMS" ]]; then
    filename="$(basename "$(dirname "$asset")")-SHA256SUMS"
  fi
  destination="$stage/$filename"
  [[ ! -e "$destination" ]] || { echo "Nome de artefato duplicado: $filename" >&2; exit 4; }
  cp "$asset" "$destination"
done < <(find "$assets_dir" -type f \( -name '*.zip' -o -name '*.tar' -o -name '*.json' -o -name '*.pdf' -o -name '*.apk' -o -name '*.aab' -o -name '*.ipa' -o -name '*.dmg' -o -name '*.msi' -o -name '*.exe' -o -name '*.deb' -o -name '*.rpm' -o -name '*.AppImage' -o -name 'SHA256SUMS' \) -not -path "$stage/*" -print0 | sort -z)
mapfile -t assets < <(find "$stage" -maxdepth 1 -type f -print | sort)
((${#assets[@]} > 0)) || { echo "Nenhum artefato publicável encontrado em $assets_dir" >&2; exit 4; }

notes="${RELEASE_NOTES_FILE:-release/RELEASE_NOTES.md}"
if gh release view "$tag" >/dev/null 2>&1; then
  echo "A release $tag já existe; versões publicadas são imutáveis." >&2
  exit 5
fi

args=(release create "$tag" "${assets[@]}" --title "PIGE360 ${version}" --prerelease --target "${GITHUB_SHA:?GITHUB_SHA ausente}")
[[ -f "$notes" ]] && args+=(--notes-file "$notes") || args+=(--generate-notes)
gh "${args[@]}"
