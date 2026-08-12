#!/bin/sh
set -u

warning() {
  printf 'WARNING: assinatura/publicação iOS ignorada: %s\n' "$*"
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

if [ -z "${APPLE_SIGNING_CERTIFICATE_BASE64:-}" ]; then
  warning 'APPLE_SIGNING_CERTIFICATE_BASE64 ausente ou vazio. Nenhum envio à App Store será realizado.'
  exit 0
fi
if [ -z "${APPLE_SIGNING_CERTIFICATE_PASSWORD:-}" ]; then
  warning 'APPLE_SIGNING_CERTIFICATE_PASSWORD ausente ou vazio. Nenhum envio à App Store será realizado.'
  exit 0
fi
if [ -z "${APPLE_SIGNING_IDENTITY:-}" ]; then
  warning 'APPLE_SIGNING_IDENTITY ausente ou vazio. Nenhum envio à App Store será realizado.'
  exit 0
fi

command -v security >/dev/null 2>&1 || { warning 'security não disponível; assinatura iOS ignorada.'; exit 0; }
command -v codesign >/dev/null 2>&1 || { warning 'codesign não disponível; assinatura iOS ignorada.'; exit 0; }
command -v ditto >/dev/null 2>&1 || { warning 'ditto não disponível; assinatura iOS ignorada.'; exit 0; }
command -v openssl >/dev/null 2>&1 || { warning 'openssl não disponível; assinatura iOS ignorada.'; exit 0; }

tmp="$(mktemp -d)"
keychain="$tmp/pige360.keychain-db"
password="$(openssl rand -hex 24 2>/dev/null || true)"
cleanup() { security delete-keychain "$keychain" >/dev/null 2>&1 || true; rm -rf "$tmp"; }
trap cleanup EXIT INT TERM

if [ -z "$password" ] || ! printf '%s' "$APPLE_SIGNING_CERTIFICATE_BASE64" | decode_base64 > "$tmp/signing.p12" 2>/dev/null; then
  warning 'certificado Apple em Base64 inválido. Nenhum envio à App Store será realizado.'
  exit 0
fi

if ! security create-keychain -p "$password" "$keychain" >/dev/null 2>&1 \
  || ! security set-keychain-settings -lut 21600 "$keychain" >/dev/null 2>&1 \
  || ! security unlock-keychain -p "$password" "$keychain" >/dev/null 2>&1 \
  || ! security import "$tmp/signing.p12" -k "$keychain" -P "$APPLE_SIGNING_CERTIFICATE_PASSWORD" -T /usr/bin/codesign >/dev/null 2>&1 \
  || ! security set-key-partition-list -S apple-tool:,apple:,codesign: -s -k "$password" "$keychain" >/dev/null 2>&1; then
  warning 'certificado, senha ou chave Apple inválida. Nenhum envio à App Store será realizado.'
  exit 0
fi

security list-keychains -d user -s "$keychain" >/dev/null 2>&1 || {
  warning 'não foi possível ativar o chaveiro Apple; assinatura iOS ignorada.'
  exit 0
}

profile_dir="$HOME/Library/MobileDevice/Provisioning Profiles"
profile=''
if [ -n "${APPLE_PROVISIONING_PROFILE_BASE64:-}" ]; then
  mkdir -p "$profile_dir"
  profile="$profile_dir/pige360.mobileprovision"
  if ! printf '%s' "$APPLE_PROVISIONING_PROFILE_BASE64" | decode_base64 > "$profile" 2>/dev/null; then
    warning 'perfil de provisionamento Apple inválido; assinatura foi ignorada.'
    exit 0
  fi
fi

mkdir -p release/artifacts/ios/signed
found=0
for app in $(find apps -type d \( -path '*/src-tauri/gen/apple/build/*/*.app' -o -path '*/src-tauri/target/*/release/bundle/macos/*.app' \)); do
  [ -d "$app" ] || continue
  found=1
  name="$(basename "$app" .app)"
  backup="$tmp/$name-before-sign.app"
  cp -R "$app" "$backup"
  if [ -n "$profile" ]; then cp "$profile" "$app/embedded.mobileprovision"; fi
  if ! codesign --force --deep --options runtime --timestamp --sign "$APPLE_SIGNING_IDENTITY" "$app" >/dev/null 2>&1 \
    || ! codesign --verify --deep --strict "$app" >/dev/null 2>&1; then
    rm -rf "$app"
    cp -R "$backup" "$app"
    warning "certificado Apple rejeitado para $name.app. O aplicativo original foi preservado."
    exit 0
  fi
  work="$tmp/$name"
  output="$(pwd)/release/artifacts/ios/signed/${name}.ipa"
  mkdir -p "$work/Payload"
  cp -R "$app" "$work/Payload/"
  if ! (cd "$work" && ditto -c -k --sequesterRsrc --keepParent Payload "$output") >/dev/null 2>&1; then
    warning "não foi possível empacotar $name.app; nenhum envio à App Store será realizado."
    exit 0
  fi
done

if [ "$found" -eq 0 ]; then
  warning 'nenhum aplicativo iOS foi encontrado para assinatura.'
else
  printf 'Assinatura iOS concluída; publicação em loja permanece desativada.\n'
fi
exit 0
