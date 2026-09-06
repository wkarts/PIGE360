#!/usr/bin/env python3
"""Valida o PIGE360 Deployer integrado e sua política exclusiva x64."""

from __future__ import annotations

import json
import re
import tomllib
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]
DEPLOYER = ROOT / "tools/pige360-deployer"


def read(relative: str) -> str:
    path = ROOT / relative
    if not path.is_file():
        raise RuntimeError(f"arquivo obrigatório ausente: {relative}")
    return path.read_text(encoding="utf-8")


def main() -> int:
    failures: list[str] = []
    version = read("VERSION").strip()
    required = (
        "tools/pige360-deployer/package.json",
        "tools/pige360-deployer/package-lock.json",
        "tools/pige360-deployer/src-tauri/Cargo.toml",
        "tools/pige360-deployer/src-tauri/Cargo.lock",
        "tools/pige360-deployer/src-tauri/tauri.conf.json",
        "tools/pige360-deployer/src-tauri/src/bin/pige360-deploy-agent.rs",
        "tools/pige360-deployer/src-tauri/src/deployer/agent.rs",
        "tools/pige360-deployer/src-tauri/src/deployer/desktop.rs",
        "tools/pige360-deployer/src-tauri/build.rs",
        "tools/pige360-deployer/src/pages/DeploymentPage.vue",
        "tools/pige360-deployer/CONTRATO.md",
        ".github/workflows/35-build-deployer.yml",
        ".github/workflows/36-develop-prerelease.yml",
        ".github/workflows/50-release.yml",
    )
    for relative in required:
        if not (ROOT / relative).is_file():
            failures.append(f"arquivo obrigatório ausente: {relative}")

    if failures:
        print(json.dumps({"status": "failed", "failures": failures}, ensure_ascii=False))
        return 1

    package = json.loads(read("tools/pige360-deployer/package.json"))
    lock = json.loads(read("tools/pige360-deployer/package-lock.json"))
    tauri = json.loads(read("tools/pige360-deployer/src-tauri/tauri.conf.json"))
    cargo = tomllib.loads(read("tools/pige360-deployer/src-tauri/Cargo.toml"))
    cargo_lock = read("tools/pige360-deployer/src-tauri/Cargo.lock")
    cargo_lock_match = re.search(
        r'^\[\[package\]\]\s*\nname\s*=\s*"pige360_deployer"\s*\nversion\s*=\s*"([^"]+)"',
        cargo_lock,
        re.MULTILINE,
    )
    nested_version = read("tools/pige360-deployer/VERSION").strip()
    observed = {
        "package": package.get("version"),
        "package_lock": lock.get("version"),
        "package_lock_root": lock.get("packages", {}).get("", {}).get("version"),
        "tauri": tauri.get("version"),
        "cargo": cargo.get("package", {}).get("version"),
        "cargo_lock": cargo_lock_match.group(1) if cargo_lock_match else None,
        "version_file": nested_version,
    }
    for name, value in observed.items():
        if value != version:
            failures.append(f"versão do Deployer divergente em {name}: {value!r} != {version!r}")

    build_rs = read("tools/pige360-deployer/src-tauri/build.rs")
    desktop_rs = read("tools/pige360-deployer/src-tauri/src/deployer/desktop.rs")
    agent_rs = read("tools/pige360-deployer/src-tauri/src/deployer/agent.rs")
    page = read("tools/pige360-deployer/src/pages/DeploymentPage.vue")
    contract = read("tools/pige360-deployer/CONTRATO.md")
    if "pige360-deploy-agent-linux-amd64" not in build_rs:
        failures.append("build.rs não incorpora o agente Linux AMD64")
    for relative, content in (
        ("build.rs", build_rs),
        ("desktop.rs", desktop_rs),
        ("DeploymentPage.vue", page),
    ):
        if re.search(r"AGENT_LINUX_ARM64|pige360-deploy-agent-linux-arm64|aarch64", content, re.I):
            failures.append(f"{relative} ainda contém agente ARM64 operacional")
    if "x86_64/amd64" not in desktop_rs:
        failures.append("desktop.rs não informa a restrição x86_64/amd64")
    if "não compila nem distribui ARM64" not in contract:
        failures.append("contrato não declara a exclusão de ARM64 do implantador")
    for required_text in (
        "service-native-image-only", "pige360-secrets-init", "pige360-secret-set",
        "pige360-backup", "pige360-readiness", "rollback_now",
    ):
        if required_text not in agent_rs:
            failures.append(f"agente service-native não contém {required_text}")
    for forbidden_text in ("install.sh", "validate.sh", "update.sh", "rollback.sh", "init-secrets.sh"):
        if forbidden_text in agent_rs:
            failures.append(f"agente ainda depende de script de host: {forbidden_text}")
    if "vX.Y.Z-rc.N" in page or "v1.0.0-rc.1" in page:
        failures.append("interface ainda oferece prerelease RC incompatível com develop-<sha12>")

    for relative in (".github/workflows/35-build-deployer.yml", ".github/workflows/36-develop-prerelease.yml"):
        text = read(relative)
        try:
            yaml.safe_load(text)
        except yaml.YAMLError as exc:
            failures.append(f"workflow inválido {relative}: {exc}")
        for required_text in (
            "x86_64-unknown-linux-gnu",
            "x86_64-pc-windows-msvc",
            "x86_64-apple-darwin",
            "pige360-deploy-agent-linux-amd64",
        ):
            if required_text not in text:
                failures.append(f"{relative} não contém {required_text}")
        if re.search(r"ubuntu-[^\n]*-arm|aarch64|linux-arm64|macos-arm64", text, re.I):
            failures.append(f"{relative} contém alvo ARM64 proibido para o implantador")

    release = read(".github/workflows/50-release.yml")
    for required_text in (
        "deployer_agent:",
        "deployer_desktop:",
        "release-deployer-agent-linux-x64",
        "release-deployer-windows-x64",
        "release-deployer-linux-x64",
        "release-deployer-macos-x64",
    ):
        if required_text not in release:
            failures.append(f"release coordenada não contém {required_text}")

    develop_release = read(".github/workflows/36-develop-prerelease.yml")
    for required_text in (
        "github.event.workflow_run.head_sha", "refs/heads/develop",
        'tag="develop-${short_sha}"', "--prerelease", "contents: write",
    ):
        if required_text not in develop_release:
            failures.append(f"pré-release develop não contém {required_text}")

    for workflow in ("35-build-deployer.yml", "36-develop-prerelease.yml", "50-release.yml"):
        canonical = ROOT / ".github/workflows" / workflow
        mirrored = ROOT / "CI_CD_KIT_LOCAL/workflows" / workflow
        if not mirrored.is_file() or canonical.read_bytes() != mirrored.read_bytes():
            failures.append(f"workflow sem espelho idêntico: {workflow}")

    result = {
        "schema_version": 1,
        "status": "passed" if not failures else "failed",
        "version": version,
        "architectures": ["linux-amd64", "windows-x64", "linux-x64", "macos-x64"],
        "arm64_in_deployer_pipeline": False,
        "failures": failures,
    }
    print(json.dumps(result, ensure_ascii=False))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
