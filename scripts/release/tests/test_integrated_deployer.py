from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]


def load_sync_version():
    path = ROOT / "scripts/release/sync-version.py"
    spec = importlib.util.spec_from_file_location("pige360_sync_version_test", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_integrated_deployer_contract() -> None:
    result = subprocess.run(
        [sys.executable, "scripts/validation/validate_integrated_deployer.py"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_version_sync_includes_integrated_deployer() -> None:
    module = load_sync_version()
    paths = {path.relative_to(ROOT).as_posix() for path in module.metadata_paths()}
    assert "tools/pige360-deployer/VERSION" in paths
    assert "tools/pige360-deployer/package-lock.json" in paths
    assert "tools/pige360-deployer/src-tauri/Cargo.toml" in paths
    assert "tools/pige360-deployer/src-tauri/Cargo.lock" in paths
    assert "tools/pige360-deployer/src-tauri/tauri.conf.json" in paths


def test_deployer_workflows_are_x64_only() -> None:
    for relative in (
        ".github/workflows/35-build-deployer.yml",
        ".github/workflows/36-develop-prerelease.yml",
    ):
        text = (ROOT / relative).read_text(encoding="utf-8").lower()
        assert "x86_64-unknown-linux-gnu" in text
        assert "x86_64-pc-windows-msvc" in text
        assert "x86_64-apple-darwin" in text
        assert "aarch64" not in text
        assert "linux-arm64" not in text
        assert "macos-arm64" not in text
