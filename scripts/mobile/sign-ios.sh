#!/bin/sh
set -eu
[ -n "${APPLE_SIGNING_CERTIFICATE_BASE64:-}" ] || { echo 'SKIPPED_NOT_CONFIGURED: APPLE_SIGNING_CERTIFICATE_BASE64 ausente.'; exit 0; }
: "${APPLE_SIGNING_CERTIFICATE_PASSWORD:?APPLE_SIGNING_CERTIFICATE_PASSWORD obrigatório}"
: "${APPLE_SIGNING_IDENTITY:?APPLE_SIGNING_IDENTITY obrigatório}"
command -v security >/dev/null 2>&1 || { echo 'security não disponível; execute em macOS.' >&2; exit 3; }
command -v codesign >/dev/null 2>&1 || { echo 'codesign não disponível; execute em macOS.' >&2; exit 3; }
command -v ditto >/dev/null 2>&1 || { echo 'ditto não disponível; execute em macOS.' >&2; exit 3; }
tmp="$(mktemp -d)"; keychain="$tmp/pige360.keychain-db"; password="$(openssl rand -hex 24)"
cleanup(){ security delete-keychain "$keychain" >/dev/null 2>&1 || true; rm -rf "$tmp"; }
trap cleanup EXIT INT TERM
printf '%s' "$APPLE_SIGNING_CERTIFICATE_BASE64" | base64 -d > "$tmp/signing.p12"
security create-keychain -p "$password" "$keychain"
security set-keychain-settings -lut 21600 "$keychain"
security unlock-keychain -p "$password" "$keychain"
security import "$tmp/signing.p12" -k "$keychain" -P "$APPLE_SIGNING_CERTIFICATE_PASSWORD" -T /usr/bin/codesign
security set-key-partition-list -S apple-tool:,apple:,codesign: -s -k "$password" "$keychain" >/dev/null
security list-keychains -d user -s "$keychain" $(security list-keychains -d user | tr -d '"')
profile_dir="$HOME/Library/MobileDevice/Provisioning Profiles"; mkdir -p "$profile_dir"
if [ -n "${APPLE_PROVISIONING_PROFILE_BASE64:-}" ]; then
  profile="$profile_dir/pige360.mobileprovision"; printf '%s' "$APPLE_PROVISIONING_PROFILE_BASE64" | base64 -d > "$profile"
fi
mkdir -p release/artifacts/ios/signed
found=0
find apps -type d -path '*/src-tauri/gen/apple/build/*/*.app' -o -type d -path '*/src-tauri/target/*/release/bundle/macos/*.app' | while IFS= read -r app; do
  [ -d "$app" ] || continue
  found=1
  if [ -n "${APPLE_PROVISIONING_PROFILE_BASE64:-}" ] && [ -d "$app" ]; then cp "$profile" "$app/embedded.mobileprovision"; fi
  codesign --force --deep --options runtime --timestamp --sign "$APPLE_SIGNING_IDENTITY" "$app"
  codesign --verify --deep --strict "$app"
  name="$(basename "$app" .app)"; work="$tmp/$name"; mkdir -p "$work/Payload"; cp -R "$app" "$work/Payload/"
  (cd "$work" && ditto -c -k --sequesterRsrc --keepParent Payload "$OLDPWD/release/artifacts/ios/signed/${name}.ipa")
done
echo 'Assinatura iOS concluída para os .app localizados.'
