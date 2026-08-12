from __future__ import annotations

import hashlib
import json
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[3]
GLOBAL_APPS = {"platform-console", "branding-studio"}
ALL_APPS = {
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


def test_official_branding_archive_is_complete_and_active_tree_is_safe() -> None:
    manifest_path = ROOT / "docs/design/reference-assets/manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    archive = ROOT / manifest["source_archive"]

    assert manifest["schema_version"] == 2
    assert manifest["files_count"] == 119
    assert manifest["assets_count"] == 118
    assert manifest["active_files_count"] == 115
    assert manifest["source_only_files_count"] == 4
    assert manifest["integrity"]["internal_checksum_entries"] == 118
    assert manifest["integrity"]["internal_checksums_verified"] == 118
    assert hashlib.sha256(archive.read_bytes()).hexdigest() == manifest["source_archive_sha256"]

    brand_root = ROOT / "packages/tenant-branding/brands/platform-pige360"
    active = [item for item in manifest["files"] if item["activation_status"] == "active"]
    source_only = [item for item in manifest["files"] if item["activation_status"] == "source_only_not_extracted"]
    assert len(active) == 115
    assert len(source_only) == 4
    for item in active:
        path = brand_root / item["path"]
        assert path.is_file(), item["path"]
        assert hashlib.sha256(path.read_bytes()).hexdigest() == item["sha256"]
    for item in source_only:
        assert not (brand_root / item["path"]).exists()


def test_all_pwa_and_tauri_manifests_reference_real_icons() -> None:
    global_digest = hashlib.sha256(
        (ROOT / "packages/tenant-branding/brands/platform-pige360/02_ICONS/pwa/icon-192.png").read_bytes()
    ).hexdigest()
    tenant_digests: set[str] = set()

    for app_name in sorted(ALL_APPS):
        app = ROOT / "apps" / app_name
        manifest = json.loads((app / "public/manifest.webmanifest").read_text(encoding="utf-8"))
        assert len(manifest["icons"]) == 2
        for icon in manifest["icons"]:
            path = app / "public" / icon["src"]
            assert path.is_file(), f"{app_name}: {icon['src']}"
            with Image.open(path) as image:
                expected = tuple(int(value) for value in icon["sizes"].split("x"))
                assert image.size == expected
        digest = hashlib.sha256((app / "public/icon-192.png").read_bytes()).hexdigest()
        if app_name in GLOBAL_APPS:
            assert digest == global_digest
        else:
            assert digest != global_digest
            tenant_digests.add(digest)

        tauri_path = app / "src-tauri/tauri.conf.json"
        tauri = json.loads(tauri_path.read_text(encoding="utf-8"))
        declared = tauri["bundle"]["icon"]
        assert declared == [
            "icons/32x32.png",
            "icons/128x128.png",
            "icons/128x128@2x.png",
            "icons/icon.icns",
            "icons/icon.ico",
        ]
        for relative in declared:
            assert (tauri_path.parent / relative).is_file(), f"{app_name}: {relative}"

    assert len(tenant_digests) == 1


def test_operational_tree_uses_only_current_product_identity() -> None:
    needle = ("projeto" + " " + "escola" + " " + "360").casefold()
    ignored_parts = {".recovery", ".pytest_cache", "__pycache__", "release"}
    binary_suffixes = {".png", ".jpg", ".jpeg", ".webp", ".ico", ".icns", ".zip", ".tar", ".gz", ".pdf"}
    violations: list[str] = []
    for path in ROOT.rglob("*"):
        if not path.is_file() or any(part in ignored_parts for part in path.parts):
            continue
        if path.suffix.lower() in binary_suffixes:
            continue
        content = path.read_text(encoding="utf-8", errors="ignore").casefold().replace("º", "").replace("°", "")
        if needle in content:
            violations.append(path.relative_to(ROOT).as_posix())
    assert violations == []
