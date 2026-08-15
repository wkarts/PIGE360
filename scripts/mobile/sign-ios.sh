#!/bin/sh
set -eu

required="${SIGN_REQUIRED:-false}"
requested="${SIGN_REQUESTED:-false}"

fail_or_skip() {
  if [ "$required" = 'true' ] || [ "$requested" = 'true' ]; then
    printf 'ERROR: assinatura iOS obrigatória: %s\n' "$*" >&2
    exit 4
  fi
  printf 'INFO: assinatura iOS não solicitada: %s\n' "$*"
  exit 0
}

decode_base64() {
  if base64 --decode </dev/null >/dev/null 2>&1; then base64 --decode; else base64 -D; fi
}

if [ "$required" != 'true' ] && [ "$requested" != 'true' ]; then
  printf 'INFO: nenhum IPA será declarado publicável sem certificado e perfil Apple.\n'
  exit 0
fi

for variable in APPLE_SIGNING_CERTIFICATE_BASE64 APPLE_SIGNING_CERTIFICATE_PASSWORD APPLE_SIGNING_IDENTITY APPLE_PROVISIONING_PROFILE_BASE64; do
  eval "value=\${$variable:-}"
  [ -n "$value" ] || fail_or_skip "variável $variable ausente"
done

for tool in security codesign ditto openssl; do command -v "$tool" >/dev/null 2>&1 || fail_or_skip "$tool não disponível"; done

tmp="$(mktemp -d)"
keychain="$tmp/pige360.keychain-db"
password="$(openssl rand -hex 24 2>/dev/null || true)"
cleanup() { security delete-keychain "$keychain" >/dev/null 2>&1 || true; rm -rf "$tmp"; }
trap cleanup EXIT INT TERM

[ -n "$password" ] || fail_or_skip 'não foi possível criar senha efêmera para o chaveiro'
printf '%s' "$APPLE_SIGNING_CERTIFICATE_BASE64" | decode_base64 > "$tmp/signing.p12" 2>/dev/null || fail_or_skip 'certificado Apple em Base64 inválido'
security create-keychain -p "$password" "$keychain" >/dev/null 2>&1
security set-keychain-settings -lut 21600 "$keychain" >/dev/null 2>&1
security unlock-keychain -p "$password" "$keychain" >/dev/null 2>&1
security import "$tmp/signing.p12" -k "$keychain" -P "$APPLE_SIGNING_CERTIFICATE_PASSWORD" -T /usr/bin/codesign >/dev/null 2>&1
security set-key-partition-list -S apple-tool:,apple:,codesign: -s -k "$password" "$keychain" >/dev/null 2>&1
security list-keychains -d user -s "$keychain" >/dev/null 2>&1

profile_dir="$HOME/Library/MobileDevice/Provisioning Profiles"
mkdir -p "$profile_dir"
profile="$profile_dir/pige360.mobileprovision"
printf '%s' "$APPLE_PROVISIONING_PROFILE_BASE64" | decode_base64 > "$profile" 2>/dev/null || fail_or_skip 'perfil de provisionamento Apple inválido'
security cms -D -i "$profile" >/dev/null 2>&1 || fail_or_skip 'perfil de provisionamento Apple não pôde ser lido'

signed_dir='release/artifacts/ios/signed'
mkdir -p "$signed_dir"
found=0
signed_count=0
for app in $(find apps -type d \( -path '*/src-tauri/gen/apple/build/*/*.app' -o -path '*/src-tauri/target/*/release/bundle/macos/*.app' \)); do
  [ -d "$app" ] || continue
  found=1
  name="$(basename "$app" .app)"
  cp "$profile" "$app/embedded.mobileprovision"
  entitlements="$tmp/$name.entitlements"
  codesign -d --entitlements :- "$app" > "$entitlements" 2>/dev/null || true
  if [ -s "$entitlements" ]; then
    codesign --force --deep --sign "$APPLE_SIGNING_IDENTITY" --entitlements "$entitlements" "$app"
  else
    codesign --force --deep --sign "$APPLE_SIGNING_IDENTITY" "$app"
  fi
  codesign --verify --deep --strict "$app"
  work="$tmp/$name"
  mkdir -p "$work/Payload"
  cp -R "$app" "$work/Payload/"
  output="$signed_dir/${name}.ipa"
  (cd "$work" && ditto -c -k --sequesterRsrc --keepParent Payload "$output")
  signed_count=$((signed_count + 1))
done

[ "$found" -eq 1 ] || fail_or_skip 'nenhum aplicativo iOS foi encontrado para assinatura'
expected="${EXPECTED_IOS_ARTIFACTS:-5}"
[ "$signed_count" -eq "$expected" ] || fail_or_skip "esperadas $expected IPAs assinadas; encontradas $signed_count"

if [ "$required" = 'true' ]; then
  find release/artifacts/ios -maxdepth 1 -type f -name '*.ipa' -delete
  find "$signed_dir" -maxdepth 1 -type f -name '*.ipa' -exec mv {} release/artifacts/ios/ \;
  rmdir "$signed_dir" 2>/dev/null || true
fi
(cd release/artifacts/ios && sha256sum ./*.ipa > SHA256SUMS)
printf 'Assinatura iOS concluída e verificada; os IPAs publicados contêm perfil de provisionamento e assinatura Apple.\n'
