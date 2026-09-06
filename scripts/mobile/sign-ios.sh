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

for tool in security codesign ditto openssl unzip; do command -v "$tool" >/dev/null 2>&1 || fail_or_skip "$tool não disponível"; done
if command -v sha256sum >/dev/null 2>&1; then
  checksum_write() { sha256sum "$@"; }
  checksum_check() { sha256sum --check "$1"; }
elif command -v shasum >/dev/null 2>&1; then
  checksum_write() { shasum -a 256 "$@"; }
  checksum_check() { shasum -a 256 --check "$1"; }
else
  fail_or_skip 'sha256sum ou shasum não disponível'
fi

tmp="$(mktemp -d)"
keychain="$tmp/pige360.keychain-db"
password="$(openssl rand -hex 24 2>/dev/null || true)"
profile=''
cleanup() {
  security delete-keychain "$keychain" >/dev/null 2>&1 || true
  [ -z "$profile" ] || rm -f "$profile"
  rm -rf "$tmp"
}
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
profile="$profile_dir/pige360-${GITHUB_RUN_ID:-$$}.mobileprovision"
printf '%s' "$APPLE_PROVISIONING_PROFILE_BASE64" | decode_base64 > "$profile" 2>/dev/null || fail_or_skip 'perfil de provisionamento Apple inválido'
security cms -D -i "$profile" >/dev/null 2>&1 || fail_or_skip 'perfil de provisionamento Apple não pôde ser lido'

root_dir="$(pwd)"
signed_dir="$root_dir/release/artifacts/ios/signed"
mkdir -p "$signed_dir"
found=0
signed_count=0
for app_archive in "$root_dir"/release/artifacts/ios/*-ios-arm64-unsigned.app.zip; do
  [ -f "$app_archive" ] || continue
  found=1
  work="$tmp/app-$signed_count"
  mkdir -p "$work"
  unzip -q "$app_archive" -d "$work"
  app="$(find "$work" -maxdepth 2 -type d -name '*.app' -print | sort | head -n 1)"
  [ -n "$app" ] || fail_or_skip "bundle .app ausente em $(basename "$app_archive")"
  name="$(basename "$app" .app)"
  cp "$profile" "$app/embedded.mobileprovision"
  entitlements="$tmp/$signed_count-$name.entitlements"
  codesign -d --entitlements :- "$app" > "$entitlements" 2>/dev/null || true
  if [ -s "$entitlements" ]; then
    codesign --force --deep --sign "$APPLE_SIGNING_IDENTITY" --entitlements "$entitlements" "$app"
  else
    codesign --force --deep --sign "$APPLE_SIGNING_IDENTITY" "$app"
  fi
  codesign --verify --deep --strict "$app"
  payload="$tmp/payload-$signed_count"
  mkdir -p "$payload/Payload"
  cp -R "$app" "$payload/Payload/"
  archive_name="$(basename "$app_archive")"
  archive_name="${archive_name%-unsigned.app.zip}"
  output="$signed_dir/${archive_name}-signed.ipa"
  (cd "$payload" && ditto -c -k --sequesterRsrc --keepParent Payload "$output")
  [ -s "$output" ] || fail_or_skip "IPA assinada vazia para $archive_name"
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
(
  cd release/artifacts/ios
  find . -type f -name '*.ipa' -print | sort \
    | while IFS= read -r ipa; do checksum_write "$ipa"; done > SHA256SUMS
  [ -s SHA256SUMS ] || fail_or_skip 'nenhuma IPA disponível para checksum'
  checksum_check SHA256SUMS
)
printf 'Assinatura iOS concluída e verificada; os IPAs publicados contêm perfil de provisionamento e assinatura Apple.\n'
