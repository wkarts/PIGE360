#!/bin/sh
set -eu
[ -n "${ANDROID_KEYSTORE_BASE64:-}" ] || { echo 'SKIPPED_NOT_CONFIGURED: ANDROID_KEYSTORE_BASE64 ausente.'; exit 0; }
: "${ANDROID_KEYSTORE_PASSWORD:?ANDROID_KEYSTORE_PASSWORD obrigatório}"
: "${ANDROID_KEY_ALIAS:?ANDROID_KEY_ALIAS obrigatório}"
: "${ANDROID_KEY_PASSWORD:?ANDROID_KEY_PASSWORD obrigatório}"
command -v apksigner >/dev/null 2>&1 || { echo 'apksigner não disponível.' >&2; exit 3; }
command -v jarsigner >/dev/null 2>&1 || { echo 'jarsigner não disponível.' >&2; exit 3; }
tmp="$(mktemp -d)"; trap 'rm -rf "$tmp"' EXIT INT TERM
printf '%s' "$ANDROID_KEYSTORE_BASE64" | base64 -d > "$tmp/release.keystore"
find release/artifacts/android -type f -name '*.apk' | while IFS= read -r apk; do
  apksigner sign --ks "$tmp/release.keystore" --ks-key-alias "$ANDROID_KEY_ALIAS" \
    --ks-pass "pass:$ANDROID_KEYSTORE_PASSWORD" --key-pass "pass:$ANDROID_KEY_PASSWORD" "$apk"
  apksigner verify --verbose "$apk"
done
find release/artifacts/android -type f -name '*.aab' | while IFS= read -r aab; do
  jarsigner -keystore "$tmp/release.keystore" -storepass "$ANDROID_KEYSTORE_PASSWORD" \
    -keypass "$ANDROID_KEY_PASSWORD" -sigalg SHA256withRSA -digestalg SHA-256 "$aab" "$ANDROID_KEY_ALIAS"
  jarsigner -verify "$aab" >/dev/null
done
echo 'Assinatura Android concluída.'
