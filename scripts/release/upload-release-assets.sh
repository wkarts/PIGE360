#!/usr/bin/env bash
set -euo pipefail

tag="${1:?tag da release obrigatório}"
shift
repo="${GITHUB_REPOSITORY:?GITHUB_REPOSITORY obrigatório}"

if [ "$#" -eq 0 ]; then
  echo "Informe ao menos um arquivo ou diretório de artefatos." >&2
  exit 2
fi

files=()
for item in "$@"; do
  if [ -d "$item" ]; then
    while IFS= read -r file; do
      files+=("$file")
    done < <(find "$item" -maxdepth 1 -type f -print | sort)
  elif [ -f "$item" ]; then
    files+=("$item")
  else
    echo "Artefato não encontrado: $item" >&2
    exit 3
  fi
done

if [ "${#files[@]}" -eq 0 ]; then
  echo "Nenhum artefato para publicar." >&2
  exit 4
fi

upload_one() {
  local file="$1"
  local name
  local attempt=1
  local max_attempts=8
  local output=""
  local wait_seconds
  name="$(basename "$file")"

  while [ "$attempt" -le "$max_attempts" ]; do
    # Torna reruns idempotentes. Uma execução interrompida pode ter deixado
    # somente parte dos assets na release draft.
    gh release delete-asset "$tag" "$name" --yes --repo "$repo" >/dev/null 2>&1 || true
    sleep 1

    if output="$(gh release upload "$tag" "$file" --repo "$repo" 2>&1)"; then
      echo "Asset publicado: $name"
      return 0
    fi

    if printf '%s\n' "$output" | grep -Eqi \
      'secondary rate limit|HTTP 403|HTTP 422|Validation Failed|already[_ -]?exists'; then
      wait_seconds=$((attempt * 5))
      [ "$wait_seconds" -le 60 ] || wait_seconds=60
      echo "Upload transitório/idempotente falhou para $name (tentativa $attempt/$max_attempts); aguardando ${wait_seconds}s." >&2
      printf '%s\n' "$output" >&2
      sleep "$wait_seconds"
      attempt=$((attempt + 1))
      continue
    fi

    printf '%s\n' "$output" >&2
    return 1
  done

  echo "Falha ao publicar $name após $max_attempts tentativas." >&2
  return 1
}

for file in "${files[@]}"; do
  upload_one "$file"
done
