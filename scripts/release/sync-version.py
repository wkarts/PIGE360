#!/usr/bin/env python3
"""Sincroniza a versão SemVer canônica sem alterar dependências externas."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
VERSION_FILE = ROOT / "VERSION"
STABLE_SEMVER_RE = re.compile(r"(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)")
SEMVER_VALUE_RE = re.compile(
    r"(?P<prefix>[~^]?)(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)"
    r"(?:-[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?"
)


def _paths(pattern: str) -> list[Path]:
    return sorted(path for path in ROOT.glob(pattern) if path.is_file())


def metadata_paths() -> list[Path]:
    patterns = (
        "package.json",
        "package-lock.json",
        "README.md",
        ".env.example",
        "deploy/env/*.env.example",
        "compose*.yaml",
        "backend/pyproject.toml",
        "backend/app/bootstrap/config.py",
        "infra/docker/**/Dockerfile*",
        "rust/Cargo.toml",
        "apps/**/package.json",
        "apps/**/src-tauri/Cargo.toml",
        "apps/**/src-tauri/tauri.conf.json",
        "apps/**/src-tauri/gen/ios/PIGE360/Info.plist",
        "apps/**/src/app-contract.ts",
        "apps/**/src/app-contract.js",
        "apps/**/public/sw.js",
        "packages/**/package.json",
        "tools/pige360-deployer/VERSION",
        "tools/pige360-deployer/package.json",
        "tools/pige360-deployer/package-lock.json",
        "tools/pige360-deployer/app.manifest.example.json",
        "tools/pige360-deployer/deploy/cloudpanel/package.json",
        "tools/pige360-deployer/src/assets/branding/brand.json",
        "tools/pige360-deployer/src/config/projectConfig.ts",
        "tools/pige360-deployer/src-tauri/Cargo.toml",
        "tools/pige360-deployer/src-tauri/Cargo.lock",
        "tools/pige360-deployer/src-tauri/tauri.conf.json",
        "docs/api/openapi.json",
        "docs/api/openapi.yaml",
        "docs/api/OPENAPI_REPORT.json",
    )
    return sorted({path for pattern in patterns for path in _paths(pattern)})


def _set_internal_dependencies(document: dict[str, Any], target: str) -> bool:
    changed = False
    for section in ("dependencies", "devDependencies", "peerDependencies", "optionalDependencies"):
        dependencies = document.get(section)
        if not isinstance(dependencies, dict):
            continue
        for name, value in list(dependencies.items()):
            if not name.startswith("@pige360/") or not isinstance(value, str):
                continue
            match = SEMVER_VALUE_RE.fullmatch(value)
            if match and value != match.group("prefix") + target:
                dependencies[name] = match.group("prefix") + target
                changed = True
    return changed


def _json_transform(path: Path, text: str, target: str) -> str:
    document = json.loads(text)
    relative = path.relative_to(ROOT).as_posix()
    changed = False

    if path.name == "package-lock.json":
        if document.get("version") != target:
            document["version"] = target
            changed = True
        packages = document.get("packages", {})
        if isinstance(packages, dict):
            for name, package in packages.items():
                # Nunca toque em node_modules: versões, URLs e integridades ali
                # pertencem a dependências externas e são imutáveis.
                if relative == "package-lock.json" and name != "" and not name.startswith(("apps/", "packages/")):
                    continue
                if relative != "package-lock.json" and name != "":
                    continue
                if not isinstance(package, dict):
                    continue
                if package.get("version") != target:
                    package["version"] = target
                    changed = True
                changed = _set_internal_dependencies(package, target) or changed
    elif relative.endswith("package.json"):
        if document.get("version") != target:
            document["version"] = target
            changed = True
        changed = _set_internal_dependencies(document, target) or changed
    elif relative in {
        "tools/pige360-deployer/app.manifest.example.json",
        "tools/pige360-deployer/src/assets/branding/brand.json",
    }:
        if document.get("version") != target:
            document["version"] = target
            changed = True
    elif relative.endswith("tauri.conf.json"):
        if document.get("version") != target:
            document["version"] = target
            changed = True
    elif relative == "docs/api/openapi.json":
        info = document.setdefault("info", {})
        if info.get("version") != target:
            info["version"] = target
            changed = True
    elif relative == "docs/api/OPENAPI_REPORT.json":
        if document.get("version") != target:
            document["version"] = target
            changed = True

    if not changed:
        return text
    return json.dumps(document, ensure_ascii=False, indent=2) + "\n"


def _replace(pattern: str, replacement: str, text: str, *, count: int = 0) -> str:
    return re.sub(pattern, replacement, text, count=count, flags=re.MULTILINE)


def _text_transform(path: Path, text: str, target: str) -> str:
    relative = path.relative_to(ROOT).as_posix()

    if relative == "README.md":
        return _replace(r"^(\*\*Versão de testes:\s*)[^*]+(\*\*)$", rf"\g<1>{target}\2", text)
    if relative == "tools/pige360-deployer/VERSION":
        return target + "\n"
    if relative == ".env.example" or (
        relative.startswith("deploy/env/") and path.name.endswith(".env.example")
    ):
        text = _replace(r"^(APP_VERSION=).*$", rf"\g<1>{target}", text)
        return _replace(
            r"^(PIGE360_IMAGE_TAG=)(?:\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?)$",
            rf"\g<1>{target}",
            text,
        )
    if path.name.startswith("compose") and path.suffix == ".yaml":
        text = _replace(r"(\$\{APP_VERSION:-)[^}]+(\})", rf"\g<1>{target}\2", text)
        return _replace(
            r"(\$\{PIGE360_IMAGE_TAG:-)(?:\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?)(\})",
            rf"\g<1>{target}\2",
            text,
        )
    if relative == "backend/pyproject.toml":
        return _replace(r"^(\[project\][\s\S]*?^version\s*=\s*\")[^\"]+(\")", rf"\g<1>{target}\2", text, count=1)
    if relative == "backend/app/bootstrap/config.py":
        text = _replace(r'^(\s*version:\s*str\s*=\s*")[^"]+("\s*)$', rf"\g<1>{target}\2", text)
        return _replace(r'(os\.getenv\("APP_VERSION",\s*")[^"]+("\))', rf"\g<1>{target}\2", text)
    if path.name.startswith("Dockerfile"):
        text = _replace(r"^(ARG VERSION=).*$", rf"\g<1>{target}", text)
        return _replace(
            r"^(ARG [A-Z0-9_]+_IMAGE=pige360-[A-Za-z0-9._-]+:).*$",
            rf"\g<1>{target}",
            text,
        )
    if path.name == "Cargo.toml":
        section = r"workspace\.package" if relative == "rust/Cargo.toml" else "package"
        return _replace(
            rf"^(\[{section}\][\s\S]*?^version\s*=\s*\")[^\"]+(\")",
            rf"\g<1>{target}\2",
            text,
            count=1,
        )
    if relative == "tools/pige360-deployer/src-tauri/Cargo.lock":
        return _replace(
            r'^(\[\[package\]\]\s*\nname\s*=\s*"pige360_deployer"\s*\nversion\s*=\s*")[^"]+("\s*)$',
            rf"\g<1>{target}\2",
            text,
            count=1,
        )
    if path.name == "Info.plist":
        return _replace(
            r"(<key>CFBundleShortVersionString</key>\s*<string>)[^<]+(</string>)",
            rf"\g<1>{target}\2",
            text,
            count=1,
        )
    if path.name in {"app-contract.ts", "app-contract.js"}:
        return _replace(r'(\bversion:\s*")[^"]+("\s*,)', rf"\g<1>{target}\2", text, count=1)
    if relative == "tools/pige360-deployer/src/config/projectConfig.ts":
        return _replace(r'(\bversion:\s*")[^"]+("\s*,)', rf"\g<1>{target}\2", text, count=1)
    if path.name == "sw.js":
        scoped = _replace(
            r"(const\s+CACHE\s*=\s*`\$\{CACHE_PREFIX\}\$\{scopePath\}-)[^`]+(`;)",
            rf"\g<1>{target}\2",
            text,
            count=1,
        )
        if scoped != text:
            return scoped
        # Compatibilidade com shells PWA anteriores ao cache por escopo.
        return _replace(r'(const\s+CACHE\s*=\s*"pige360-[^"]+-)[^"]+(";)', rf"\g<1>{target}\2", text, count=1)
    if relative == "docs/api/openapi.yaml":
        return _replace(r"^(info:\s*\n(?:^[ \t]+.*\n)*?^[ \t]+version:\s*).*$", rf"\g<1>{target}", text, count=1)
    return text


def transform(path: Path, text: str, target: str) -> str:
    if path.suffix == ".json" or path.name == "package-lock.json":
        return _json_transform(path, text, target)
    return _text_transform(path, text, target)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("version", nargs="?", help="Versão alvo X.Y.Z; por padrão usa VERSION")
    parser.add_argument("--from-version", dest="from_version", help="Mantido por compatibilidade e auditoria")
    parser.add_argument("--check", action="store_true", help="Verifica os campos canônicos sem modificar arquivos")
    args = parser.parse_args()

    current = VERSION_FILE.read_text(encoding="utf-8").strip()
    target = (args.version or current).strip()
    if not STABLE_SEMVER_RE.fullmatch(target):
        raise SystemExit(f"Versão SemVer estável inválida: {target}. Use somente X.Y.Z.")
    if args.from_version and not SEMVER_VALUE_RE.fullmatch(args.from_version.strip()):
        raise SystemExit(f"Versão de origem inválida: {args.from_version}.")

    changed: list[str] = []
    for path in metadata_paths():
        original = path.read_text(encoding="utf-8")
        updated = transform(path, original, target)
        if updated == original:
            continue
        changed.append(path.relative_to(ROOT).as_posix())
        if not args.check:
            path.write_text(updated, encoding="utf-8")

    if VERSION_FILE.read_text(encoding="utf-8").strip() != target:
        changed.insert(0, "VERSION")
        if not args.check:
            VERSION_FILE.write_text(target + "\n", encoding="utf-8")

    if args.check:
        if changed:
            print(f"Metadados divergentes de {target}:")
            for item in changed:
                print(f" - {item}")
            return 1
        print(f"Metadados compatíveis com {target}.")
        return 0

    print(f"Versão canônica: {target}")
    if args.from_version:
        print(f"Versão de origem declarada: {args.from_version.strip()}")
    print(f"Arquivos atualizados: {len(changed)}")
    for item in changed:
        print(f" - {item}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
