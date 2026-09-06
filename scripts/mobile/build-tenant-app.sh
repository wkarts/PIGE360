#!/bin/sh
set -eu

manifest="${1:?manifest obrigatório}"
app="${2:?app obrigatório}"
platform="${3:?plataforma obrigatória}"
root_dir="$(pwd)"
python_cmd='python3'
command -v "$python_cmd" >/dev/null 2>&1 || python_cmd='python'
command -v "$python_cmd" >/dev/null 2>&1 || { echo 'Python 3 é obrigatório.' >&2; exit 3; }
if command -v sha256sum >/dev/null 2>&1; then
  checksum_write() { sha256sum "$@"; }
  checksum_check() { sha256sum --check "$1"; }
elif command -v shasum >/dev/null 2>&1; then
  checksum_write() { shasum -a 256 "$@"; }
  checksum_check() { shasum -a 256 --check "$1"; }
else
  echo 'sha256sum ou shasum é obrigatório.' >&2
  exit 3
fi

case "$app" in ''|*[!a-z0-9-]*) echo "Aplicativo inválido: $app" >&2; exit 2 ;; esac
case "$platform" in android|ios|windows|linux|macos|pwa) ;; *) echo "Plataforma inválida: $platform" >&2; exit 2 ;; esac
version="$(tr -d '[:space:]' < VERSION)"
prerelease_id='(0|[1-9][0-9]*|[0-9A-Za-z-]*[A-Za-z-][0-9A-Za-z-]*)'
semver_re="^(0|[1-9][0-9]*)\\.(0|[1-9][0-9]*)\\.(0|[1-9][0-9]*)(-${prerelease_id}(\\.${prerelease_id})*)?(\\+[0-9A-Za-z-]+(\\.[0-9A-Za-z-]+)*)?$"
printf '%s\n' "$version" | grep -Eq "$semver_re" || {
  echo "Versão SemVer inválida para o app white-label: $version" >&2
  exit 4
}

"$python_cmd" scripts/validation/tenant_app_manifest.py "$manifest" >/dev/null
source_app="${app}-app"
[ -d "apps/$source_app" ] || source_app="$app"
[ -d "apps/$source_app" ] || { echo "Workspace não localizado para $app." >&2; exit 2; }

output_dir="$root_dir/release/artifacts/tenant-apps/$app/$platform"
rm -rf "$output_dir"
mkdir -p "$output_dir"

runtime_path="$root_dir/apps/$source_app/public/tenant-app-manifest.json"
tauri_path="$root_dir/apps/$source_app/src-tauri/tauri.conf.json"
runtime_backup="$(mktemp "${TMPDIR:-/tmp}/pige360-tenant-runtime.XXXXXX")"
tauri_backup="$(mktemp "${TMPDIR:-/tmp}/pige360-tenant-tauri.XXXXXX")"
runtime_existed=false
if [ -f "$runtime_path" ]; then cp "$runtime_path" "$runtime_backup"; runtime_existed=true; fi
if [ -f "$tauri_path" ]; then cp "$tauri_path" "$tauri_backup"; fi

cleanup() {
  if [ "$runtime_existed" = true ]; then cp "$runtime_backup" "$runtime_path"; else rm -f "$runtime_path"; fi
  if [ -s "$tauri_backup" ]; then cp "$tauri_backup" "$tauri_path"; fi
  rm -f "$runtime_backup" "$tauri_backup"
}
trap cleanup EXIT HUP INT TERM

# Fixa tenant, URLs, allowlist, identidade e nome antes de qualquer build. O
# aplicativo dedicado não pode oferecer troca arbitrária de tenant em runtime.
"$python_cmd" - "$manifest" "$app" "$platform" "$runtime_path" "$tauri_path" <<'PY'
import hashlib
import json
import sys
import urllib.parse
from pathlib import Path

import yaml

manifest_path = Path(sys.argv[1])
app_name, platform = sys.argv[2], sys.argv[3]
runtime_path, tauri_path = Path(sys.argv[4]), Path(sys.argv[5])
manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
app = (manifest.get("apps") or {}).get(app_name)
if not isinstance(app, dict) or not app.get("enabled"):
    raise SystemExit(f"Aplicativo {app_name} não está habilitado no manifesto")
if platform not in app.get("platforms", []):
    raise SystemExit(f"Plataforma {platform} não foi autorizada para {app_name}")

urls = {field: str(app.get(field, "")) for field in ("api_url", "web_url", "update_url")}
hosts = []
for field, value in urls.items():
    parsed = urllib.parse.urlparse(value)
    local = parsed.hostname in {"localhost", "127.0.0.1"} or str(parsed.hostname).endswith(".localhost")
    if not parsed.hostname or (parsed.scheme != "https" and not (parsed.scheme == "http" and local)):
        raise SystemExit(f"{field} deve usar HTTPS e possuir hostname válido")
    hosts.append(parsed.hostname)

runtime = {
    "schema_version": 1,
    "tenant_id": str(manifest["tenant_id"]),
    "tenant_code": str(manifest["tenant_code"]),
    "app_product": app_name,
    "display_name": str(app["display_name"]),
    "identifier": str(app["identifier"]),
    **urls,
    "allowed_hosts": sorted(set(hosts)),
    "brand_version": int(manifest["brand_version"]),
    "manifest_version": int(manifest["manifest_version"]),
    "release_channel": str(manifest["release_channel"]),
    "features": app.get("features", {}),
    "manifest_sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
    "build_job_id": "github-actions",
}
runtime_path.parent.mkdir(parents=True, exist_ok=True)
runtime_path.write_text(json.dumps(runtime, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")

if platform != "pwa":
    if not tauri_path.is_file():
        raise SystemExit(f"Configuração Tauri ausente: {tauri_path}")
    config = json.loads(tauri_path.read_text(encoding="utf-8"))
    config["productName"] = runtime["display_name"]
    config["identifier"] = runtime["identifier"]
    security = config.setdefault("app", {}).setdefault("security", {})
    connect = " ".join(f"https://{host}" for host in runtime["allowed_hosts"])
    security["csp"] = (
        "default-src 'self'; img-src 'self' data: blob:; "
        f"style-src 'self' 'unsafe-inline'; connect-src 'self' {connect}"
    )
    tauri_path.write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
PY

case "$platform" in
  android)
    bash scripts/mobile/build-android.sh --app "$source_app" --profile debug --artifacts apk --targets aarch64 --verify-signature
    find release/artifacts/android -maxdepth 1 -type f -name '*.apk' -exec cp {} "$output_dir/" \;
    ;;
  ios)
    bash scripts/mobile/build-ios.sh --mode local-signing --app "$source_app"
    find release/artifacts/ios -maxdepth 1 -type f ! -name SHA256SUMS -exec cp {} "$output_dir/" \;
    ;;
  windows|linux|macos)
    target="${TAURI_TARGET:?TAURI_TARGET obrigatório}"
    case "$platform:$target" in
      windows:x86_64-pc-windows-msvc|linux:x86_64-unknown-linux-gnu|macos:aarch64-apple-darwin) ;;
      *) echo "Target $target incompatível com a plataforma $platform." >&2; exit 2 ;;
    esac
    command -v cargo >/dev/null 2>&1 || { echo 'Cargo é obrigatório para build desktop.' >&2; exit 3; }
    if [ "${RUNNER_OS:-}" = 'Windows' ]; then
      perl_binary="${PIGE360_STRAWBERRY_PERL:-}"
      [ -n "$perl_binary" ] || { echo 'PIGE360_STRAWBERRY_PERL é obrigatório no Windows.' >&2; exit 3; }
      case "$perl_binary" in
        [A-Za-z]:\\*)
          command -v cygpath >/dev/null 2>&1 || { echo 'cygpath é obrigatório no Git Bash.' >&2; exit 3; }
          perl_binary="$(cygpath -u "$perl_binary")"
          ;;
      esac
      [ -x "$perl_binary" ] || { echo "Strawberry Perl inválido: $perl_binary" >&2; exit 3; }
      export PATH="$(dirname "$perl_binary"):$PATH"
      perl -MLocale::Maketext::Simple -e 1
    fi
    lockfile="$root_dir/apps/$source_app/src-tauri/Cargo.lock"
    if [ ! -f "$lockfile" ]; then
      if [ "${PIGE360_REQUIRE_LOCKED:-false}" = 'true' ]; then
        echo "Cargo.lock obrigatório e ausente: $lockfile" >&2
        exit 4
      fi
      cargo generate-lockfile --manifest-path "$root_dir/apps/$source_app/src-tauri/Cargo.toml"
    fi
    cargo metadata --manifest-path "$root_dir/apps/$source_app/src-tauri/Cargo.toml" --locked --format-version 1 >/dev/null
    bash scripts/frontend/install-dependencies.sh
    if [ -n "${PIGE360_CARGO_TARGET_ROOT:-}" ]; then
      cargo_target_dir="${PIGE360_CARGO_TARGET_ROOT%/}/$source_app"
    elif [ "${RUNNER_OS:-}" = 'Windows' ]; then
      cargo_target_dir="C:/pige360-target/${GITHUB_RUN_ID:-local}/$source_app"
    else
      cargo_target_dir="$root_dir/apps/$source_app/src-tauri/target"
    fi
    (
      cd "apps/$source_app"
      export CARGO_TARGET_DIR="$cargo_target_dir"
      npx --no-install tauri build --target "$target"
    )
    bundle="$cargo_target_dir/$target/release/bundle"
    [ -d "$bundle" ] || { echo "Bundle desktop ausente: $bundle" >&2; exit 4; }
    tar -czf "$output_dir/PIGE360-v${version}-${app}-${platform}-${target}.tar.gz" -C "$bundle" .
    ;;
  pwa)
    command -v zip >/dev/null 2>&1 || { echo 'zip é obrigatório para o pacote PWA.' >&2; exit 3; }
    command -v unzip >/dev/null 2>&1 || { echo 'unzip é obrigatório para validar o pacote PWA.' >&2; exit 3; }
    bash scripts/frontend/install-dependencies.sh
    npm --workspace "./apps/$source_app" run build
    dist="apps/$source_app/dist"
    [ -d "$dist" ] || { echo "PWA não gerada: $dist" >&2; exit 4; }
    archive="$output_dir/PIGE360-v${version}-${app}-pwa.zip"
    (cd "$dist" && zip -qr "$archive" .)
    unzip -tq "$archive" >/dev/null
    ;;
esac

artifact_count="$(find "$output_dir" -maxdepth 1 -type f ! -name SHA256SUMS | wc -l | tr -d '[:space:]')"
[ "$artifact_count" -gt 0 ] || { echo "Build $app/$platform não produziu artefato." >&2; exit 4; }
(
  cd "$output_dir"
  checksum_write ./* > SHA256SUMS
  checksum_check SHA256SUMS
)
printf 'Tenant app: app=%s plataforma=%s artefatos=%s\n' "$app" "$platform" "$artifact_count"
