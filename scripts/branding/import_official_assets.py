#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import mimetypes
import os
import re
import shutil
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from PIL import Image
import cairosvg

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ARCHIVE = ROOT / "docs/design/reference-assets/originals/PIGE360_BRANDING_COMPLETO.zip"
BRAND_ROOT = ROOT / "packages/tenant-branding/brands/platform-pige360"
DEMO_BRAND_ROOT = ROOT / "packages/tenant-branding/brands/demo-horizonte"
MANIFEST_PATH = ROOT / "docs/design/reference-assets/manifest.json"
REFERENCE_MAP = ROOT / "docs/design/reference-map/REFERENCE_MAP.md"
EVIDENCE_PATH = ROOT / "docs/execution/evidence/branding-import-report.json"
TOKENS_ROOT = ROOT / "packages/design-tokens/src"

GLOBAL_APPS = {"platform-console", "branding-studio"}
PWA_APPS = {
    "admin-app",
    "branding-studio",
    "desktop-admin",
    "family-app",
    "kiosk-app",
    "platform-console",
    "pos-app",
    "public-portal",
    "student-app",
    "teacher-app",
    "tenant-admin-web",
    "tenant-download-center",
    "timeclock-app",
}


class BrandingImportError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class Asset:
    path: str
    sha256: str
    bytes: int
    media_type: str
    category: str


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def safe_member(name: str) -> PurePosixPath:
    path = PurePosixPath(name)
    if path.is_absolute() or ".." in path.parts:
        raise BrandingImportError(f"Entrada insegura no ZIP: {name}")
    return path


def category_for(path: str) -> str:
    first = path.split("/", 1)[0]
    return {
        "00_MASTER": "master",
        "01_LOGOS": "logos",
        "02_ICONS": "icons",
        "03_SPLASH": "splash",
        "04_SOCIAL": "social",
        "05_APP_BRANDING": "app_branding",
        "06_DOCUMENTS": "documents",
        "07_PRESENTATION_BOARDS": "presentation_boards",
        "08_RECONSTRUCTED_REFERENCES": "reconstructed_references",
        "09_DESIGN_TOKENS": "design_tokens",
        "10_SOURCE_REFERENCES": "source_references",
    }.get(first, "metadata")


def parse_checksum_file(text: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for line_number, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if not line:
            continue
        match = re.fullmatch(r"([0-9a-fA-F]{64})\s{2}(.+)", line)
        if not match:
            raise BrandingImportError(f"Linha inválida em SHA256SUMS.txt: {line_number}")
        digest, relative = match.groups()
        safe_member(relative)
        if relative in result:
            raise BrandingImportError(f"Entrada duplicada em SHA256SUMS.txt: {relative}")
        result[relative] = digest.lower()
    return result


def inspect_archive(archive: Path) -> tuple[list[Asset], dict[str, bytes], dict[str, Any]]:
    if not archive.is_file():
        raise BrandingImportError(f"Arquivo de branding não localizado: {archive}")
    payloads: dict[str, bytes] = {}
    with zipfile.ZipFile(archive) as bundle:
        corrupt = bundle.testzip()
        if corrupt:
            raise BrandingImportError(f"Entrada corrompida no ZIP: {corrupt}")
        files = [item for item in bundle.infolist() if not item.is_dir()]
        if not files:
            raise BrandingImportError("O ZIP de branding está vazio.")
        roots = {safe_member(item.filename).parts[0] for item in files}
        if roots != {"PIGE360_BRANDING_COMPLETO"}:
            raise BrandingImportError(f"Raiz inesperada no ZIP: {sorted(roots)}")
        for item in files:
            member = safe_member(item.filename)
            relative = PurePosixPath(*member.parts[1:]).as_posix()
            if not relative:
                continue
            if relative in payloads:
                raise BrandingImportError(f"Arquivo duplicado no ZIP: {relative}")
            payloads[relative] = bundle.read(item)

    checksum_payload = payloads.get("SHA256SUMS.txt")
    if checksum_payload is None:
        raise BrandingImportError("SHA256SUMS.txt não existe no pacote oficial.")
    expected = parse_checksum_file(checksum_payload.decode("utf-8"))
    missing = sorted(set(expected) - set(payloads))
    unexpected = sorted(set(payloads) - set(expected) - {"SHA256SUMS.txt"})
    mismatches = [
        path for path, digest in expected.items()
        if path in payloads and sha256_bytes(payloads[path]) != digest
    ]
    if missing or unexpected or mismatches:
        raise BrandingImportError(
            "Integridade interna inválida: "
            + json.dumps({"missing": missing, "unexpected": unexpected, "mismatches": mismatches}, ensure_ascii=False)
        )

    assets = [
        Asset(
            path=path,
            sha256=sha256_bytes(data),
            bytes=len(data),
            media_type=mimetypes.guess_type(path)[0] or "application/octet-stream",
            category=category_for(path),
        )
        for path, data in sorted(payloads.items())
    ]
    integrity = {
        "zip_valid": True,
        "unsafe_entries": 0,
        "internal_checksum_entries": len(expected),
        "internal_checksums_verified": len(expected),
        "missing": [],
        "unexpected": [],
        "mismatches": [],
    }
    return assets, payloads, integrity


def atomic_extract(payloads: dict[str, bytes]) -> None:
    BRAND_ROOT.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="pige360-branding-", dir=str(BRAND_ROOT.parent)) as temporary:
        staging = Path(temporary) / BRAND_ROOT.name
        for relative, data in payloads.items():
            # Referências-fonte históricas permanecem preservadas somente no ZIP original.
            # A árvore ativa contém exclusivamente ativos nominais PIGE360.
            if relative.startswith("10_SOURCE_REFERENCES/"):
                continue
            target = staging / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
        previous = BRAND_ROOT.with_name(BRAND_ROOT.name + ".previous")
        if previous.exists():
            shutil.rmtree(previous)
        if BRAND_ROOT.exists():
            BRAND_ROOT.replace(previous)
        staging.replace(BRAND_ROOT)
        if previous.exists():
            shutil.rmtree(previous)


def copy_design_tokens() -> list[str]:
    TOKENS_ROOT.mkdir(parents=True, exist_ok=True)
    mapping = {
        "09_DESIGN_TOKENS/tokens.json": "tokens.json",
        "09_DESIGN_TOKENS/tokens.css": "tokens.css",
        "09_DESIGN_TOKENS/tokens.scss": "tokens.scss",
        "09_DESIGN_TOKENS/tailwind-preset.ts": "tailwind-preset.ts",
    }
    changed: list[str] = []
    for source_name, target_name in mapping.items():
        source = BRAND_ROOT / source_name
        target = TOKENS_ROOT / target_name
        target.write_bytes(source.read_bytes())
        changed.append(target.relative_to(ROOT).as_posix())
    return changed


def render_demo_icon(size: int) -> bytes:
    source = DEMO_BRAND_ROOT / "logo-symbol.svg"
    if not source.is_file():
        raise BrandingImportError("Logo do tenant demonstrativo não localizado.")
    return cairosvg.svg2png(bytestring=source.read_bytes(), output_width=size, output_height=size)


def write_icon_set(icon_source: Path | None, destination: Path, *, demo: bool) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    if demo:
        source_bytes = render_demo_icon(1024)
        source_path = destination / ".icon-source.png"
        source_path.write_bytes(source_bytes)
    else:
        if icon_source is None or not icon_source.is_file():
            raise BrandingImportError("Ícone global de 1024 px não localizado.")
        source_path = icon_source
    with Image.open(source_path) as original:
        image = original.convert("RGBA")
        for name, size in (("32x32.png", 32), ("128x128.png", 128), ("128x128@2x.png", 256), ("icon.png", 512)):
            resized = image.resize((size, size), Image.Resampling.LANCZOS)
            resized.save(destination / name, format="PNG", optimize=True)
        image.resize((256, 256), Image.Resampling.LANCZOS).save(
            destination / "icon.ico", format="ICO", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
        )
        image.save(destination / "icon.icns", format="ICNS", sizes=[(16, 16), (32, 32), (64, 64), (128, 128), (256, 256), (512, 512), (1024, 1024)])
    if demo and source_path.name == ".icon-source.png":
        source_path.unlink(missing_ok=True)


def update_pwa_and_tauri() -> list[str]:
    changed: list[str] = []
    global_icon = BRAND_ROOT / "02_ICONS/pige360-1024x1024.png"
    for app_name in sorted(PWA_APPS):
        app_root = ROOT / "apps" / app_name
        if not app_root.is_dir():
            continue
        public = app_root / "public"
        public.mkdir(parents=True, exist_ok=True)
        global_context = app_name in GLOBAL_APPS
        if global_context:
            icon192 = BRAND_ROOT / "02_ICONS/pwa/icon-192.png"
            icon512 = BRAND_ROOT / "02_ICONS/pwa/icon-512.png"
            (public / "icon-192.png").write_bytes(icon192.read_bytes())
            (public / "icon-512.png").write_bytes(icon512.read_bytes())
        else:
            (public / "icon-192.png").write_bytes(render_demo_icon(192))
            (public / "icon-512.png").write_bytes(render_demo_icon(512))
        manifest_path = public / "manifest.webmanifest"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.is_file() else {}
        manifest["icons"] = [
            {"src": "icon-192.png", "sizes": "192x192", "type": "image/png", "purpose": "any maskable"},
            {"src": "icon-512.png", "sizes": "512x512", "type": "image/png", "purpose": "any maskable"},
        ]
        manifest.setdefault("display", "standalone")
        manifest.setdefault("start_url", "./")
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        changed.extend([
            (public / "icon-192.png").relative_to(ROOT).as_posix(),
            (public / "icon-512.png").relative_to(ROOT).as_posix(),
            manifest_path.relative_to(ROOT).as_posix(),
        ])

        tauri_config = app_root / "src-tauri/tauri.conf.json"
        if tauri_config.is_file():
            icons = tauri_config.parent / "icons"
            if icons.exists():
                shutil.rmtree(icons)
            write_icon_set(global_icon if global_context else None, icons, demo=not global_context)
            config = json.loads(tauri_config.read_text(encoding="utf-8"))
            bundle = config.setdefault("bundle", {})
            bundle["icon"] = [
                "icons/32x32.png",
                "icons/128x128.png",
                "icons/128x128@2x.png",
                "icons/icon.icns",
                "icons/icon.ico",
            ]
            tauri_config.write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            changed.append(tauri_config.relative_to(ROOT).as_posix())
            changed.extend(p.relative_to(ROOT).as_posix() for p in sorted(icons.iterdir()) if p.is_file())
    return changed


def write_manifest(archive: Path, assets: list[Asset], integrity: dict[str, Any]) -> None:
    result = {
        "schema_version": 2,
        "generated_locally": True,
        "source_archive": archive.relative_to(ROOT).as_posix() if archive.is_relative_to(ROOT) else archive.name,
        "source_archive_sha256": sha256_file(archive),
        "source_archive_bytes": archive.stat().st_size,
        "files_count": len(assets),
        "assets_count": len([asset for asset in assets if asset.path != "SHA256SUMS.txt"]),
        "active_files_count": len([asset for asset in assets if not asset.path.startswith("10_SOURCE_REFERENCES/")]),
        "source_only_files_count": len([asset for asset in assets if asset.path.startswith("10_SOURCE_REFERENCES/")]),
        "integrity": integrity,
        "files": [
            {
                "path": asset.path,
                "sha256": asset.sha256,
                "bytes": asset.bytes,
                "media_type": asset.media_type,
                "category": asset.category,
                "source": "PIGE360_BRANDING_COMPLETO.zip",
                "activation_status": "source_only_not_extracted" if asset.path.startswith("10_SOURCE_REFERENCES/") else "active",
            }
            for asset in assets
        ],
    }
    MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST_PATH.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def update_reference_map(assets: list[Asset]) -> None:
    if not REFERENCE_MAP.is_file():
        return
    hashes = {asset.path: asset.sha256 for asset in assets}
    text = REFERENCE_MAP.read_text(encoding="utf-8")
    for relative, digest in hashes.items():
        marker = f"packages/tenant-branding/brands/platform-pige360/{relative}"
        escaped = re.escape(marker)
        text = re.sub(
            rf"(`{escaped}`\s*\|\s*`)[0-9a-f]{{64}}(`)",
            rf"\g<1>{digest}\2",
            text,
        )
    text = re.sub(r"\n## Inconsistência preservada\n.*\Z", "", text, flags=re.S)
    integrity_section = (
        "\n## Integridade do acervo\n\n"
        f"- Arquivo oficial: `docs/design/reference-assets/originals/PIGE360_BRANDING_COMPLETO.zip`.\n"
        f"- Arquivos no pacote: **{len(assets)}**.\n"
        f"- Entradas cobertas pelo checksum interno: **{len(assets) - 1}**.\n"
        "- Resultado: **todos os checksums internos foram confirmados**.\n"
        "- Quatro pranchas-fonte históricas ficam preservadas somente no ZIP original e não são ativadas nem distribuídas.\n"
        "- Os componentes consomem exclusivamente tokens, manifestos, resource packs e referências nominais PIGE360.\n"
    )
    REFERENCE_MAP.write_text(text.rstrip() + "\n" + integrity_section, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Importa e valida o acervo visual oficial do PIGE360.")
    parser.add_argument("--archive", type=Path, default=DEFAULT_ARCHIVE)
    args = parser.parse_args()
    archive = args.archive.resolve()
    assets, payloads, integrity = inspect_archive(archive)
    atomic_extract(payloads)
    token_files = copy_design_tokens()
    app_files = update_pwa_and_tauri()
    write_manifest(archive, assets, integrity)
    update_reference_map(assets)
    report = {
        "schema_version": 1,
        "status": "passed",
        "network_used": False,
        "archive": archive.relative_to(ROOT).as_posix() if archive.is_relative_to(ROOT) else str(archive),
        "archive_sha256": sha256_file(archive),
        "files_count": len(assets),
        "active_files_count": len([asset for asset in assets if not asset.path.startswith("10_SOURCE_REFERENCES/")]),
        "source_only_files_count": len([asset for asset in assets if asset.path.startswith("10_SOURCE_REFERENCES/")]),
        "internal_checksum_entries": integrity["internal_checksum_entries"],
        "internal_checksums_verified": integrity["internal_checksums_verified"],
        "design_token_files": token_files,
        "application_files_updated": app_files,
    }
    EVIDENCE_PATH.parent.mkdir(parents=True, exist_ok=True)
    EVIDENCE_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
