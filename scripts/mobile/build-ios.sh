#!/bin/sh
set -eu
command -v xcodebuild >/dev/null 2>&1 || { echo 'Xcode/xcodebuild não disponível.' >&2; exit 3; }
command -v cargo >/dev/null 2>&1 || { echo 'Rust/cargo não disponível.' >&2; exit 3; }
command -v npm >/dev/null 2>&1 || { echo 'npm não disponível.' >&2; exit 3; }

bash scripts/frontend/install-dependencies.sh
rustup target add aarch64-apple-ios x86_64-apple-ios aarch64-apple-ios-sim
mkdir -p release/artifacts/ios
rm -rf release/artifacts/ios/* 2>/dev/null || true

apps="${PIGE360_MOBILE_APPS:-family-app teacher-app student-app admin-app pos-app}"
for app in $apps; do
  [ -d "apps/$app/src-tauri" ] || { echo "Aplicação Tauri ausente: $app" >&2; exit 4; }
  (
    cd "apps/$app"
    if ! find src-tauri/gen/ios -maxdepth 2 -name '*.xcodeproj' -print -quit 2>/dev/null | grep -q .; then
      echo "Inicializando projeto iOS Tauri para $app"
      rm -rf src-tauri/gen/ios
      CI=true npx --no-install tauri ios init --ci
    fi
    echo "Compilando aplicação iOS ARM64 sem assinatura para $app"
    CI=true npx --no-install tauri ios build --target aarch64 -- -- CODE_SIGNING_ALLOWED=NO CODE_SIGNING_REQUIRED=NO CODE_SIGN_IDENTITY=""
  )

  copied=0
  while IFS= read -r ipa; do
    [ -n "$ipa" ] || continue
    copied=1
    cp "$ipa" "release/artifacts/ios/${app}-$(basename "$ipa")"
  done <<EOF
$(find "apps/$app/src-tauri" -type f -name '*.ipa' 2>/dev/null | sort)
EOF

  if [ "$copied" -eq 0 ]; then
    app_bundle="$(find "apps/$app/src-tauri" -type d -name '*.app' 2>/dev/null | head -n 1 || true)"
    if [ -n "$app_bundle" ]; then
      tmp="$(mktemp -d)"
      mkdir -p "$tmp/Payload"
      cp -R "$app_bundle" "$tmp/Payload/"
      (cd "$tmp" && /usr/bin/zip -qry "$OLDPWD/release/artifacts/ios/${app}-unsigned.ipa" Payload)
      rm -rf "$tmp"
      copied=1
    fi
  fi
  [ "$copied" -eq 1 ] || { echo "Nenhum bundle iOS/IPA gerado para $app" >&2; exit 5; }
done

test -n "$(find release/artifacts/ios -type f -name '*.ipa' -print -quit)"
find release/artifacts/ios -maxdepth 1 -type f -print | sort
