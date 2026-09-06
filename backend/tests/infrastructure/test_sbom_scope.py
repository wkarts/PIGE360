from __future__ import annotations

import json
import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[3]
VERSION = (ROOT / "VERSION").read_text(encoding="utf-8").strip()


def _component(document: dict, name: str, version: str) -> dict:
    return next(
        item
        for item in document["components"]
        if item.get("name") == name and item.get("version") == version
    )


def test_sbom_includes_locked_frontend_and_production_dependencies(tmp_path: Path) -> None:
    output = tmp_path / "pige360.cdx.json"
    process = subprocess.run(
        [
            sys.executable,
            "scripts/supply-chain/generate_sbom.py",
            "--network-used",
            "--output",
            str(output),
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert process.returncode == 0, process.stderr or process.stdout

    document = json.loads(output.read_text(encoding="utf-8"))
    assert document["bomFormat"] == "CycloneDX"
    assert document["specVersion"] == "1.6"
    properties = {item["name"]: item["value"] for item in document["properties"]}
    assert properties["pige360:network-used"] == "true"
    assert properties["pige360:npm-resolution"] == "package-lock-v3"
    assert properties["pige360:cargo-resolution"] == "manifest-only"
    assert properties["pige360:cargo-lockfiles"] == "0"
    assert properties["pige360:cargo-lockfiles-expected"] == "14"

    echarts = _component(document, "echarts", "6.1.0")
    assert echarts["purl"] == "pkg:npm/echarts@6.1.0"

    celery = _component(document, "celery", "5.5.0")
    celery_properties = {item["name"]: item["value"] for item in celery["properties"]}
    assert celery_properties["pige360:declared-in"] == "backend/requirements.production.lock"
    assert celery_properties["pige360:scope"] == "production"

    branding = _component(document, "pige360-official-branding", VERSION)
    branding_properties = {item["name"]: item["value"] for item in branding["properties"]}
    assert branding_properties["pige360:asset-count"] == branding_properties["pige360:hashed-assets"]
    branding_files = [
        item
        for item in document["components"]
        if item.get("type") == "file"
        and str(item.get("name", "")).startswith(
            "packages/tenant-branding/brands/platform-pige360/"
        )
    ]
    assert len(branding_files) == int(branding_properties["pige360:asset-count"])
    assert all(len(item.get("hashes", [])) == 1 for item in branding_files)


def _load_generator():
    path = ROOT / "scripts/supply-chain/generate_sbom.py"
    spec = importlib.util.spec_from_file_location("pige360_generate_sbom", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_cargo_locks_are_parsed_and_duplicate_provenance_is_merged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = _load_generator()
    rust_lock = tmp_path / "rust/Cargo.lock"
    app_lock = tmp_path / "apps/admin-app/src-tauri/Cargo.lock"
    rust_lock.parent.mkdir(parents=True)
    app_lock.parent.mkdir(parents=True)
    app_lock.with_name("Cargo.toml").write_text(
        '[package]\nname = "pige360-admin-app"\nversion = "1.1.0"\n',
        encoding="utf-8",
    )
    checksum = "a" * 64
    lock_text = f'''version = 3

[[package]]
name = "pige360-local"
version = "1.1.0"

[[package]]
name = "serde"
version = "1.0.217"
source = "registry+https://github.com/rust-lang/crates.io-index"
checksum = "{checksum}"
'''
    rust_lock.write_text(lock_text, encoding="utf-8")
    app_lock.write_text(lock_text, encoding="utf-8")
    monkeypatch.setattr(module, "ROOT", tmp_path)

    lockfiles = module.cargo_lock_paths()
    assert lockfiles == [rust_lock, app_lock]
    components = module.merge_components(module.cargo_lock_components(lockfiles))
    assert len(components) == 1
    serde = components[0]
    assert serde["name"] == "serde"
    assert serde["purl"] == "pkg:cargo/serde@1.0.217"
    assert serde["hashes"] == [{"alg": "SHA-256", "content": checksum}]
    resolved_in = {
        item["value"]
        for item in serde["properties"]
        if item["name"] == "pige360:resolved-in"
    }
    assert resolved_in == {
        "rust/Cargo.lock",
        "apps/admin-app/src-tauri/Cargo.lock",
    }


def test_cargo_lock_with_invalid_checksum_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = _load_generator()
    lock = tmp_path / "rust/Cargo.lock"
    lock.parent.mkdir(parents=True)
    lock.write_text(
        '''version = 3

[[package]]
name = "serde"
version = "1.0.217"
source = "registry+https://github.com/rust-lang/crates.io-index"
checksum = "not-a-sha256"
''',
        encoding="utf-8",
    )
    monkeypatch.setattr(module, "ROOT", tmp_path)

    with pytest.raises(RuntimeError, match="checksum Cargo invalido"):
        module.cargo_lock_components([lock])
