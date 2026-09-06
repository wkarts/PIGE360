#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import tomllib
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote


ROOT = Path(__file__).resolve().parents[2]
VERSION = (ROOT / "VERSION").read_text(encoding="utf-8").strip()


def bomref(kind: str, name: str, version: str) -> str:
    return hashlib.sha256(f"{kind}:{name}:{version}".encode()).hexdigest()[:32]


def component(kind: str, name: str, version: str, **extra: object) -> dict[str, object]:
    result: dict[str, object] = {
        "type": kind,
        "bom-ref": bomref(kind, name, version),
        "name": name,
        "version": version,
    }
    result.update(extra)
    return result


def python_components() -> list[dict[str, object]]:
    result: list[dict[str, object]] = []
    for filename, scope in (
        ("requirements.lock", "local-and-ci"),
        ("requirements.production.lock", "production"),
    ):
        lock = ROOT / "backend" / filename
        for raw_line in lock.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "==" not in line:
                continue
            name, version = line.split("==", 1)
            purl_name = name.split("[", 1)[0].lower().replace("_", "-")
            result.append(
                component(
                    "library",
                    name,
                    version,
                    purl=f"pkg:pypi/{purl_name}@{quote(version, safe='.-_')}",
                    properties=[
                        {"name": "pige360:declared-in", "value": f"backend/{filename}"},
                        {"name": "pige360:scope", "value": scope},
                    ],
                )
            )
    return result


def npm_components() -> list[dict[str, object]]:
    lock = json.loads((ROOT / "package-lock.json").read_text(encoding="utf-8"))
    result: list[dict[str, object]] = []
    for path, metadata in sorted(lock.get("packages", {}).items()):
        if not path or "node_modules/" not in path or not isinstance(metadata, dict):
            continue
        version = str(metadata.get("version") or "")
        if not version:
            continue
        name = str(metadata.get("name") or path.rsplit("node_modules/", 1)[-1])
        properties = [{"name": "pige360:lock-path", "value": path}]
        if metadata.get("dev") is True:
            scope = "development"
        elif metadata.get("optional") is True:
            scope = "optional"
        else:
            scope = "runtime"
        properties.append({"name": "pige360:scope", "value": scope})
        result.append(
            component(
                "library",
                name,
                version,
                purl=f"pkg:npm/{quote(name, safe='@/')}@{quote(version, safe='.-_')}",
                properties=properties,
            )
        )
    return result


def first_party_components() -> list[dict[str, object]]:
    result: list[dict[str, object]] = []
    packages = sorted((ROOT / "apps").glob("*/package.json")) + sorted(
        (ROOT / "packages").glob("*/package.json")
    )
    for package in packages:
        data = json.loads(package.read_text(encoding="utf-8"))
        kind = "application" if package.parent.parent.name == "apps" else "library"
        result.append(
            component(
                kind,
                data.get("name", package.parent.name),
                data.get("version", VERSION),
                properties=[
                    {"name": "pige360:path", "value": package.parent.relative_to(ROOT).as_posix()}
                ],
            )
        )
    return result


def expected_cargo_lock_paths() -> list[Path]:
    candidates = [ROOT / "rust" / "Cargo.lock"]
    candidates.extend(
        manifest.with_name("Cargo.lock")
        for manifest in sorted((ROOT / "apps").glob("*/src-tauri/Cargo.toml"))
    )
    return candidates


def cargo_lock_paths() -> list[Path]:
    """Return only the lockfiles that define the shipped Rust workspaces."""

    return [path for path in expected_cargo_lock_paths() if path.is_file()]


def cargo_lock_components(lockfiles: list[Path]) -> list[dict[str, object]]:
    """Describe resolved Cargo packages without claiming resolution when locks are absent."""

    result: list[dict[str, object]] = []
    for lock in lockfiles:
        try:
            document = tomllib.loads(lock.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError) as exc:
            raise RuntimeError(f"Cargo.lock invalido: {lock}: {exc}") from exc
        packages = document.get("package", [])
        if not isinstance(packages, list):
            raise RuntimeError(f"Cargo.lock sem lista package: {lock}")
        for package in packages:
            if not isinstance(package, dict):
                raise RuntimeError(f"entrada package invalida em {lock}")
            name = str(package.get("name") or "").strip()
            version = str(package.get("version") or "").strip()
            if not name or not version:
                raise RuntimeError(f"pacote Cargo sem nome/versao em {lock}")
            # Packages without a source are local workspace/path packages. They
            # are already described from their manifests with the correct
            # application/library type; do not duplicate them as libraries.
            if not package.get("source"):
                continue
            extra: dict[str, object] = {
                "purl": f"pkg:cargo/{quote(name)}@{quote(version, safe='.-_')}",
                "properties": [
                    {
                        "name": "pige360:resolved-in",
                        "value": lock.relative_to(ROOT).as_posix(),
                    },
                    {"name": "pige360:resolution", "value": "cargo-lock"},
                ],
            }
            checksum = str(package.get("checksum") or "").strip().lower()
            if checksum:
                if not re.fullmatch(r"[0-9a-f]{64}", checksum):
                    raise RuntimeError(f"checksum Cargo invalido para {name} {version} em {lock}")
                extra["hashes"] = [{"alg": "SHA-256", "content": checksum}]
            result.append(component("library", name, version, **extra))
    return result


def rust_components(lockfiles: list[Path]) -> list[dict[str, object]]:
    result: list[dict[str, object]] = []
    lockfile_set = {path.resolve() for path in lockfiles}
    manifests = sorted((ROOT / "rust" / "crates").glob("*/Cargo.toml"))
    manifests += sorted((ROOT / "apps").glob("*/src-tauri/Cargo.toml"))
    for manifest in manifests:
        text = manifest.read_text(encoding="utf-8")
        match = re.search(r'^name\s*=\s*"([^"]+)"', text, re.MULTILINE)
        name = match.group(1) if match else manifest.parent.name
        lockfile = (
            ROOT / "rust" / "Cargo.lock"
            if manifest.is_relative_to(ROOT / "rust" / "crates")
            else manifest.with_name("Cargo.lock")
        )
        resolution = "cargo-lock" if lockfile.resolve() in lockfile_set else "manifest-only"
        result.append(
            component(
                "application" if "src-tauri" in manifest.parts else "library",
                name,
                VERSION,
                purl=f"pkg:cargo/{quote(name)}@{quote(VERSION, safe='.-_')}",
                properties=[
                    {"name": "pige360:declared-in", "value": manifest.relative_to(ROOT).as_posix()},
                    {
                        "name": "pige360:resolution",
                        "value": resolution,
                    },
                ],
            )
        )
    return result


def merge_components(items: list[dict[str, object]]) -> list[dict[str, object]]:
    """Deduplicate components without discarding lock/source provenance."""

    unique: dict[object, dict[str, object]] = {}
    for item in items:
        reference = item["bom-ref"]
        if reference not in unique:
            unique[reference] = item
            continue
        current = unique[reference]
        for field in ("properties", "hashes"):
            values = current.setdefault(field, [])
            incoming = item.get(field, [])
            if isinstance(values, list) and isinstance(incoming, list):
                for value in incoming:
                    if value not in values:
                        values.append(value)
    return sorted(
        unique.values(),
        key=lambda item: (str(item["type"]), str(item["name"]), str(item["version"])),
    )


def container_components() -> list[dict[str, object]]:
    result: list[dict[str, object]] = []
    for dockerfile in sorted((ROOT / "infra" / "docker").rglob("Dockerfile*")):
        text = dockerfile.read_text(encoding="utf-8")
        for image in re.findall(r"^FROM\s+([^\s]+)", text, re.MULTILINE):
            if image.startswith("pige360-") or image.startswith("${"):
                continue
            name, separator, version = image.rpartition(":")
            if not separator:
                name, version = image, "unpinned"
            result.append(
                component(
                    "container",
                    name,
                    version,
                    properties=[
                        {"name": "pige360:declared-in", "value": dockerfile.relative_to(ROOT).as_posix()}
                    ],
                )
            )
    return result


def branding_components() -> list[dict[str, object]]:
    brand = ROOT / "packages" / "tenant-branding" / "brands" / "platform-pige360"
    assets = [path for path in sorted(brand.rglob("*")) if path.is_file()]
    result = [
        component(
            "data",
            "pige360-official-branding",
            VERSION,
            properties=[
                {"name": "pige360:asset-count", "value": str(len(assets))},
                {"name": "pige360:hashed-assets", "value": str(len(assets))},
            ],
        )
    ]
    for path in assets:
        relative = path.relative_to(ROOT).as_posix()
        result.append(
            component(
                "file",
                relative,
                VERSION,
                hashes=[
                    {"alg": "SHA-256", "content": hashlib.sha256(path.read_bytes()).hexdigest()}
                ],
                properties=[{"name": "pige360:branding-asset", "value": "true"}],
            )
        )
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--output")
    parser.add_argument(
        "--network-used",
        action="store_true",
        help="Registra que a preparação desta entrega resolveu dependências pela rede.",
    )
    args = parser.parse_args()

    lockfiles = cargo_lock_paths()
    expected_lockfiles = expected_cargo_lock_paths()
    components = (
        python_components()
        + npm_components()
        + first_party_components()
        + rust_components(lockfiles)
        + cargo_lock_components(lockfiles)
        + container_components()
        + branding_components()
    )

    components = merge_components(components)
    network_used = args.network_used or os.getenv("PIGE360_NETWORK_USED", "").lower() == "true"
    serial = "urn:uuid:" + str(uuid.uuid5(uuid.NAMESPACE_URL, "pige360:" + VERSION + ":local-sbom"))
    sbom = {
        "bomFormat": "CycloneDX",
        "specVersion": "1.6",
        "serialNumber": serial,
        "version": 1,
        "metadata": {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "tools": {
                "components": [
                    {"type": "application", "name": "pige360-local-sbom-generator", "version": VERSION}
                ]
            },
            "component": component("application", "PIGE360", VERSION),
        },
        "components": components,
        "properties": [
            {"name": "pige360:network-used", "value": str(network_used).lower()},
            {"name": "pige360:scope", "value": "source-and-declared-runtime"},
            {"name": "pige360:npm-resolution", "value": "package-lock-v3"},
            {
                "name": "pige360:cargo-resolution",
                "value": "cargo-lock" if lockfiles else "manifest-only",
            },
            {"name": "pige360:cargo-lockfiles", "value": str(len(lockfiles))},
            {
                "name": "pige360:cargo-lockfiles-expected",
                "value": str(len(expected_lockfiles)),
            },
        ],
    }
    output = Path(args.output) if args.output else ROOT / f"release/PIGE360-{VERSION}-sbom.cdx.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(sbom, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    errors: list[str] = []
    if sbom["bomFormat"] != "CycloneDX" or sbom["specVersion"] != "1.6" or not components:
        errors.append("estrutura SBOM inválida")
    if not any(
        item.get("name") == "celery"
        and any(prop.get("value") == "production" for prop in item.get("properties", []))
        for item in components
    ):
        errors.append("dependências de produção ausentes do SBOM")
    result = {
        "status": "passed" if not errors else "failed",
        "output": str(output),
        "components": len(components),
        "network_used": network_used,
        "errors": errors,
    }
    print(json.dumps(result, ensure_ascii=False))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
