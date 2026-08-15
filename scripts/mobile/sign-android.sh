#!/bin/sh
set -eu

required="${SIGN_REQUIRED:-false}"
requested="${SIGN_REQUESTED:-false}"

fail_or_skip() {
  if [ "$required" = 'true' ] || [ "$requested" = 'true' ]; then
    printf 'ERROR: assinatura Android obrigatória: %s\n' "$*" >&2
    exit 4
  fi
  printf 'INFO: assinatura Android não solicitada: %s\n' "$*"
  exit 0
}

decode_base64() {
  if base64 --decode </dev/null >/dev/null 2>&1; then base64 --decode; else base64 -D; fi
}

if [ "$required" != 'true' ] && [ "$requested" != 'true' ]; then
  printf 'INFO: artefatos Android de validação permanecem assinados pelo keystore debug do Gradle.\n'
  exit 0
fi

for variable in ANDROID_KEYSTORE_BASE64 ANDROID_KEYSTORE_PASSWORD ANDROID_KEY_ALIAS ANDROID_KEY_PASSWORD; do
  eval "value=\${$variable:-}"
  [ -n "$value" ] || fail_or_skip "variável $variable ausente"
done

resolve_tool() {
  command -v "$1" 2>/dev/null || find "${ANDROID_HOME:-/nonexistent}/build-tools" -type f -name "$1" -print 2>/dev/null | sort | tail -n 1
}
apksigner="$(resolve_tool apksigner)"
zipalign="$(resolve_tool zipalign)"
jarsigner="$(command -v jarsigner || true)"
keytool="$(command -v keytool || true)"
[ -n "$apksigner" ] && [ -x "$apksigner" ] || fail_or_skip 'apksigner não disponível'
[ -n "$zipalign" ] && [ -x "$zipalign" ] || fail_or_skip 'zipalign não disponível'
[ -n "$jarsigner" ] || fail_or_skip 'jarsigner não disponível'
[ -n "$keytool" ] || fail_or_skip 'keytool não disponível'

tmp="$(mktemp -d)"
cleanup() { rm -rf "$tmp"; }
trap cleanup EXIT INT TERM

printf '%s' "$ANDROID_KEYSTORE_BASE64" | decode_base64 > "$tmp/release.keystore" 2>/dev/null || fail_or_skip 'ANDROID_KEYSTORE_BASE64 inválida'
"$keytool" -list -keystore "$tmp/release.keystore" -storepass "$ANDROID_KEYSTORE_PASSWORD" -alias "$ANDROID_KEY_ALIAS" >/dev/null 2>&1 || fail_or_skip 'keystore, senha ou alias inválido'

found=0
for apk in release/artifacts/android/*.apk; do
  [ -f "$apk" ] || continue
  found=1
  aligned="$tmp/$(basename "$apk").aligned"
  signed="$tmp/$(basename "$apk").signed"
  "$zipalign" -f -p 4 "$apk" "$aligned"
  "$apksigner" sign --ks "$tmp/release.keystore" --ks-key-alias "$ANDROID_KEY_ALIAS" --ks-pass "pass:$ANDROID_KEYSTORE_PASSWORD" --key-pass "pass:$ANDROID_KEY_PASSWORD" --out "$signed" "$aligned"
  "$apksigner" verify --verbose --print-certs "$signed"
  mv "$signed" "$apk"
done

for aab in release/artifacts/android/*.aab; do
  [ -f "$aab" ] || continue
  found=1
  signed="$tmp/$(basename "$aab").signed"
  "$jarsigner" -keystore "$tmp/release.keystore" -storepass "$ANDROID_KEYSTORE_PASSWORD" -keypass "$ANDROID_KEY_PASSWORD" -sigalg SHA256withRSA -digestalg SHA-256 -signedjar "$signed" "$aab" "$ANDROID_KEY_ALIAS"
  "$jarsigner" -verify -strict -certs "$signed"
  mv "$signed" "$aab"
done

[ "$found" -eq 1 ] || fail_or_skip 'nenhum APK/AAB foi encontrado para assinatura'
(cd release/artifacts/android && sha256sum ./*.apk ./*.aab > SHA256SUMS)
printf 'Assinatura Android concluída e verificada; os APKs estão prontos para distribuição fora da Play e os AABs para envio à Play.\n'
