#!/usr/bin/env python3
"""Sincroniza a versão SemVer canônica do PIGE360 nos manifests públicos."""

from __future__ import annotations

import argparse
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
VERSION_FILE = ROOT / "VERSION"
STABLE_SEMVER_RE = re.compile(r"\d+\.\d+\.\d+")
PATTERNS = (
    "package.json",
    "package-lock.json",
    "README.md",
    ".env.example",
    "compose*.yaml",
    "backend/pyproject.toml",
    "backend/app/bootstrap/config.py",
    "infra/docker/**/*.Dockerfile",
    "rust/Cargo.toml",
    "apps/**/package.json",
    "apps/**/src-tauri/Cargo.toml",
    "apps/**/src-tauri/tauri.conf.json",
    "apps/**/src-tauri/gen/ios/PIGE360/Info.plist",
    "apps/**/src/app-contract.ts",
    "apps/**/src/app-contract.js",
    "apps/**/public/sw.js",
    "packages/**/package.json",
    "docs/ci-cd/*.md",
)


def targets() -> list[Path]:
    return sorted({path for pattern in PATTERNS for path in ROOT.glob(pattern) if path.is_file()})


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("version", nargs="?", help="Versão alvo X.Y.Z; por padrão usa VERSION")
    parser.add_argument("--from-version", dest="from_version", help="Versão de origem a substituir")
    parser.add_argument("--check", action="store_true", help="Somente verifica se a versão de origem ainda aparece")
    args = parser.parse_args()

    current = VERSION_FILE.read_text(encoding="utf-8").strip()
    target = (args.version or current).strip()
    source = (args.from_version or current).strip()
    if not STABLE_SEMVER_RE.fullmatch(target):
        raise SystemExit(f"Versão SemVer estável inválida: {target}. Use somente X.Y.Z.")

    changed: list[str] = []
    remaining: list[str] = []

    for path in targets():
        original = path.read_text(encoding="utf-8")
        relative = path.relative_to(ROOT).as_posix()
        if args.check:
            if source != target and source in original:
                remaining.append(relative)
            continue
        if source == target or source not in original:
            continue
        path.write_text(original.replace(source, target), encoding="utf-8")
        changed.append(relative)

    if args.check:
        if remaining:
            print("Metadados ainda contêm a versão de origem:")
            for item in remaining:
                print(f" - {item}")
            return 1
        print(f"Metadados compatíveis com {target}.")
        return 0

    VERSION_FILE.write_text(target + "\n", encoding="utf-8")
    print(f"Versão canônica: {target}")
    print(f"Versão substituída: {source}")
    print(f"Arquivos atualizados: {len(changed)}")
    for path in changed:
        print(f" - {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
