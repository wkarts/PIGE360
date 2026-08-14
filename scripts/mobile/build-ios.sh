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
      npx --no-install tauri ios init --ci
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
