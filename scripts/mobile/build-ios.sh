#!/bin/sh
set -eu
command -v xcodebuild >/dev/null || { echo 'SKIPPED_NOT_CONFIGURED: Xcode ausente.' >&2; exit 3; }
command -v cargo >/dev/null || { echo 'SKIPPED_NOT_CONFIGURED: Rust ausente.' >&2; exit 3; }
bash scripts/frontend/install-dependencies.sh
mkdir -p release/artifacts/ios
version="$(tr -d '[:space:]' < VERSION)"
case "$version" in
  [0-9]*.[0-9]*.[0-9]*-alpha.[0-9]*) ;;
  *) echo "Versão alpha inválida para o empacotamento iOS: $version" >&2; exit 4 ;;
esac
# CFBundleShortVersionString aceita somente a tripla numérica. A versão pública
# (incluindo o canal alpha) continua canônica em VERSION e no nome do artefato.
ios_version="${version%-alpha.*}"
ios_config="{\"version\":\"$ios_version\"}"
for app in family-app teacher-app student-app admin-app pos-app; do
  (
    cd "apps/$app"
    # A árvore Apple é produto do Tauri e não fica versionada. Regenerá-la em
    # CI evita que o build dependa de arquivos criados na máquina de alguém.
    if [ "${CI:-false}" = "true" ]; then
      rm -rf src-tauri/gen/apple
    fi
    if [ ! -d src-tauri/gen/apple ]; then
      # O `ios init` também lê `CFBundleShortVersionString`. Preserve qualquer
      # configuração iOS existente, aplique a versão numérica só durante a
      # geração e restaure o arquivo antes de compilar/publicar artefatos.
      ios_platform_config='src-tauri/tauri.ios.conf.json'
      ios_platform_backup="$(mktemp)"
      if [ -f "$ios_platform_config" ]; then
        cp "$ios_platform_config" "$ios_platform_backup"
      fi
      restore_ios_platform_config() {
        if [ -s "$ios_platform_backup" ]; then
          cp "$ios_platform_backup" "$ios_platform_config"
        else
          rm -f "$ios_platform_config"
        fi
        rm -f "$ios_platform_backup"
      }
      trap restore_ios_platform_config EXIT HUP INT TERM
      python3 - "$ios_platform_config" "$ios_version" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
config = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
config["version"] = sys.argv[2]
path.write_text(json.dumps(config), encoding="utf-8")
PY
      npx --no-install tauri ios init --ci
      restore_ios_platform_config
      trap - EXIT HUP INT TERM
    fi
    [ -d src-tauri/gen/apple ] || {
      echo "Falha ao gerar o projeto iOS para $app." >&2
      exit 4
    }
    npx --no-install tauri ios build --target aarch64 --config "$ios_config"
  )
done
find apps -path '*/src-tauri/gen/apple/build/arm64/*.ipa' -type f -exec cp {} release/artifacts/ios/ \;
count="$(find release/artifacts/ios -maxdepth 1 -type f -name '*.ipa' | wc -l | tr -d '[:space:]')"
[ "$count" -eq 5 ] || { echo "Esperadas 5 IPAs unsigned; encontradas $count." >&2; exit 4; }
