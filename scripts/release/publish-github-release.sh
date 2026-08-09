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
mapfile -t assets < <(find "$assets_dir" -maxdepth 1 -type f \( -name "PIGE360-${version}-*.zip" -o -name "SHA256SUMS" -o -name "PIGE360-${version}-*.json" -o -name "PIGE360-${version}-*.pdf" \) -print | sort)
((${#assets[@]} > 0)) || { echo "Nenhum artefato local encontrado em $assets_dir" >&2; exit 4; }

notes="${RELEASE_NOTES_FILE:-release/RELEASE_NOTES.md}"
if gh release view "$tag" >/dev/null 2>&1; then
  gh release upload "$tag" "${assets[@]}" --clobber
else
  args=(release create "$tag" "${assets[@]}" --title "PIGE360 ${version}")
  [[ -f "$notes" ]] && args+=(--notes-file "$notes") || args+=(--generate-notes)
  gh "${args[@]}"
fi
