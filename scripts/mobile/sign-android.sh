#!/bin/sh
set -u

warning() {
  printf 'WARNING: assinatura/publicação Android ignorada: %s\n' "$*"
}

decode_base64() {
  if base64 --decode </dev/null >/dev/null 2>&1; then
    base64 --decode
  else
    base64 -D
  fi
}

if [ "${SIGN_REQUESTED:-false}" != "true" ]; then
  warning 'a assinatura não foi solicitada; os artefatos permanecem não assinados.'
  exit 0
fi

if [ -z "${ANDROID_KEYSTORE_BASE64:-}" ]; then
  warning 'ANDROID_KEYSTORE_BASE64 ausente ou vazio. Nenhum envio à Google Play será realizado.'
  exit 0
fi
if [ -z "${ANDROID_KEYSTORE_PASSWORD:-}" ]; then
  warning 'ANDROID_KEYSTORE_PASSWORD ausente ou vazio. Nenhum envio à Google Play será realizado.'
  exit 0
fi
if [ -z "${ANDROID_KEY_ALIAS:-}" ]; then
  warning 'ANDROID_KEY_ALIAS ausente ou vazio. Nenhum envio à Google Play será realizado.'
  exit 0
fi
if [ -z "${ANDROID_KEY_PASSWORD:-}" ]; then
  warning 'ANDROID_KEY_PASSWORD ausente ou vazio. Nenhum envio à Google Play será realizado.'
  exit 0
fi

command -v apksigner >/dev/null 2>&1 || { warning 'apksigner não disponível.'; exit 0; }
command -v jarsigner >/dev/null 2>&1 || { warning 'jarsigner não disponível.'; exit 0; }
command -v keytool >/dev/null 2>&1 || { warning 'keytool não disponível.'; exit 0; }

tmp="$(mktemp -d)"
cleanup() { rm -rf "$tmp"; }
trap cleanup EXIT INT TERM

if ! printf '%s' "$ANDROID_KEYSTORE_BASE64" | decode_base64 > "$tmp/release.keystore" 2>/dev/null; then
  warning 'ANDROID_KEYSTORE_BASE64 inválida. Nenhum envio à Google Play será realizado.'
  exit 0
fi

if ! keytool -list -keystore "$tmp/release.keystore" \
    -storepass "$ANDROID_KEYSTORE_PASSWORD" -alias "$ANDROID_KEY_ALIAS" >/dev/null 2>&1; then
  warning 'keystore, senha ou alias inválido. Nenhum envio à Google Play será realizado.'
  exit 0
fi

found=0
for apk in release/artifacts/android/*.apk; do
  [ -f "$apk" ] || continue
  found=1
  backup="$tmp/$(basename "$apk").before-sign"
  cp "$apk" "$backup"
  if ! apksigner sign --ks "$tmp/release.keystore" --ks-key-alias "$ANDROID_KEY_ALIAS" \
      --ks-pass "pass:$ANDROID_KEYSTORE_PASSWORD" --key-pass "pass:$ANDROID_KEY_PASSWORD" "$apk" \
      || ! apksigner verify --verbose "$apk" >/dev/null 2>&1; then
    cp "$backup" "$apk"
    warning "certificado Android rejeitado para $(basename "$apk"). O APK original foi preservado."
    exit 0
  fi
done

for aab in release/artifacts/android/*.aab; do
  [ -f "$aab" ] || continue
  found=1
  backup="$tmp/$(basename "$aab").before-sign"
  cp "$aab" "$backup"
  if ! jarsigner -keystore "$tmp/release.keystore" -storepass "$ANDROID_KEYSTORE_PASSWORD" \
      -keypass "$ANDROID_KEY_PASSWORD" -sigalg SHA256withRSA -digestalg SHA-256 "$aab" "$ANDROID_KEY_ALIAS" \
      || ! jarsigner -verify "$aab" >/dev/null 2>&1; then
    cp "$backup" "$aab"
    warning "certificado Android rejeitado para $(basename "$aab"). O AAB original foi preservado."
    exit 0
  fi
done

if [ "$found" -eq 0 ]; then
  warning 'nenhum APK/AAB foi encontrado para assinatura.'
else
  printf 'Assinatura Android concluída; publicação em loja permanece desativada.\n'
fi
exit 0
